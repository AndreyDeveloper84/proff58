"""Истечение неоплаченных онлайн-заказов (DRF-952).

Заказ с онлайн-оплатой держит товар 30 минут. Не оплатили — заказ отменяется,
резерв снимается, товар возвращается в продажу.

Почему это живёт в ``payments``, а не в ``orders``: перед отменой надо спросить
кассу, не прошла ли оплата на самом деле. Вебхук может не дойти — сеть, 5xx,
ретраи кассы, — и тогда локальный ``payment_status`` врёт. Отменить оплаченный
заказ хуже, чем подержать резерв лишнюю минуту, поэтому последнее слово всегда
за провайдером. ``orders`` про кассу знать не должен (CLAUDE.md §4), а
``payments`` про заказы уже знает.

Существующий janitor ``orders.tasks.release_expired_reservations`` продолжает
работать и снимает резерв у любых просроченных заказов — включая те, что оплату
не предполагают. Здесь же именно онлайн-оплата: отмена заказа + возврат товара.

Что важно знать про кассу (проверено в песочнице АТОЛ Pay 02.10.2026, DRF-2736):
неоплаченный платёж отменить НЕЛЬЗЯ — ``/cancel`` отвечает ``ORDER_NOT_PAID``,
страница оплаты продолжает работать, и срок её жизни при регистрации не задаётся.
То есть после отмены заказа покупатель всё ещё может оплатить по открытой форме.
Поэтому: (1) пока покупатель явно проходит оплату, отмену откладываем; (2) об
отмене покупателю сообщаем событием ``order_status_changed``; (3) оплату, которая
всё-таки пришла после отмены, разбирает ``transitions.apply_succeeded`` — заявкой
на возврат.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.error import URLError

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core import events
from apps.orders.models import DeliveryCalcStatus, FulfillmentStatus, Order, Sync1CStatus
from apps.orders.models import PaymentStatus as OrderPaymentStatus
from apps.orders.reservation import release_reservation

from .atolpay import service as atolpay
from .atolpay.client import AtolPayError
from .models import Payment, PaymentProvider, PaymentStatus
from .services import _yookassa_request

logger = logging.getLogger(__name__)

# Способ оплаты в заказе — снимок выбора на витрине (см. payments/api.py).
ONLINE_PAYMENT_METHOD = "online"

# Автоматика отменяет только то, за что ещё никто не взялся. Матрица переходов
# разрешает отмену и из «Собирается», и из «В доставке» — но это решение
# менеджера при возврате, а не повод роботу отменить заказ, который склад уже
# везёт. Просроченная оплата у такого заказа — случай для человека.
CANCELLABLE_BY_TIMEOUT = frozenset({FulfillmentStatus.NEW, FulfillmentStatus.CONFIRMED})

# Платёж, по которому деньги ещё могут прийти.
_LIVE_PAYMENT = (PaymentStatus.PENDING, PaymentStatus.WAITING_CAPTURE)

# Решение по коду ``/status`` кассы АТОЛ (Таблица 9 её документации, см.
# atolpay.service.PROVIDER_STATUS). Всё, чего в таблицах нет, — «не знаем»:
# отменять заказ по ответу, который мы не поняли, нельзя.
_ATOL_PAID = 1
#: Покупатель прямо сейчас проходит оплату: банк ещё не ответил, идёт 3-D Secure.
_ATOL_IN_FLIGHT = frozenset({2, 10})
#: Оплаты нет: платёж только зарегистрирован, отклонён, отменён или просрочен.
_ATOL_NOT_PAID = frozenset({0, 3, 4, 6, 9, 12})

# После стольких сбоев связи с кассой подряд прогон прерывается: при лежащей кассе
# каждый заказ ждал бы таймаут запроса, и пачка из сотен заказов заняла бы воркер
# надолго. Считаются только сбои связи (см. ``_is_outage``): ошибка по одному
# конкретному платежу повторится и завтра, и три таких заказа в начале выборки
# иначе останавливали бы автоотмену для всех остальных.
_MAX_PROVIDER_FAILURES = 3

_CANCELLED, _SKIPPED, _PROVIDER_FAILED = "cancelled", "skipped", "provider_failed"
_PAID, _IN_FLIGHT, _NOT_PAID, _UNKNOWN = "paid", "in_flight", "not_paid", "unknown"


def in_flight_grace() -> timedelta:
    """Сколько после истечения резерва ждём покупателя, который уже платит."""
    return timedelta(minutes=int(getattr(settings, "PAYMENT_IN_FLIGHT_GRACE_MINUTES", 15)))


def _yookassa_says_paid(payment: Payment) -> bool:
    """ЮKassa (прежняя касса): деньги пришли? Ошибка запроса — исключение."""
    if not payment.provider_payment_id:
        return False
    data = _yookassa_request("GET", f"payments/{payment.provider_payment_id}")
    return bool(data.get("paid")) and data.get("status") == "succeeded"


def _ask_provider(payment: Payment) -> tuple[str, int | None]:
    """Что касса говорит о платеже: (вердикт, сырой код для АТОЛ).

    Любая ошибка запроса — исключение: без ответа кассы заказ не отменяем. Молчание
    провайдера не повод отдавать чужой товар.
    """
    if payment.provider != PaymentProvider.ATOLPAY:
        return (_PAID if _yookassa_says_paid(payment) else _NOT_PAID), None
    code = atolpay.provider_status_code(payment)
    if code == _ATOL_PAID:
        return _PAID, code
    if code in _ATOL_IN_FLIGHT:
        return _IN_FLIGHT, code
    if code in _ATOL_NOT_PAID:
        return _NOT_PAID, code
    return _UNKNOWN, code


def _is_outage(exc: Exception) -> bool:
    """Касса недоступна целиком — спрашивать её про следующий заказ бессмысленно.

    Сеть, таймаут, 5xx, протухший или незаданный токен (401/403), превышен лимит
    запросов (429), вместо ответа пришло не то (шлюз отдал HTML). Остальное — касса
    не знает именно этот платёж или отказала по нему — беда одного платежа.
    """
    if isinstance(exc, AtolPayError):
        if exc.code in ("NETWORK_ERROR", "NOT_CONFIGURED", "AUTH_ERROR"):
            return True
        if exc.http_status in (401, 403, 429) or exc.http_status >= 500:
            return True
        return not exc.code and not exc.http_status  # ответ не разобран вовсе
    return isinstance(exc, URLError | TimeoutError | ConnectionError)


def _notify_cancelled(order_id: int, old_status: str) -> None:
    """Сообщить подписчикам об отмене. Сбой подписчика не роняет пачку janitor'а."""
    results = events.order_status_changed.send_robust(
        sender=Order,
        order_id=order_id,
        old_status=old_status,
        new_status=FulfillmentStatus.CANCELLED,
    )
    for receiver, response in results:
        if isinstance(response, Exception):
            logger.error(
                "Заказ %s отменён по таймауту, но подписчик %r упал: %r",
                order_id,
                receiver,
                response,
            )


def _apply_paid(order_id: int, paid: list[tuple[Payment, int | None]]) -> None:
    """Касса говорит «оплачен», а у нас платёж ещё живой: уведомление не дошло."""
    logger.warning(
        "Заказ %s: касса подтвердила оплату, отмена отменяется — "
        "уведомление, судя по всему, не дошло",
        order_id,
    )
    for payment, code in paid:
        if code is None:
            # ЮKassa: статус применяет только её собственный вебхук.
            logger.error(
                "Заказ %s: платёж ЮKassa %s оплачен, а уведомления нет — проверьте вручную",
                order_id,
                payment.provider_payment_id,
            )
            continue
        # Не ждём уведомления, которое могло потеряться: заказ становится оплаченным
        # по тому же проверенному статусу и тем же путём.
        try:
            atolpay.apply_verified_status(payment, code, source="expiry-janitor")
        except Exception:
            # Сюда попадает и сбой подписчика события оплаты: сам статус к этому
            # моменту мог уже примениться.
            logger.exception(
                "Заказ %s: оплата из кассы применена не полностью (платёж %s)",
                order_id,
                payment.pk,
            )


def _expire(order_id: int) -> tuple[str, bool]:
    """Истечь один онлайн-заказ.

    Возвращает (исход, ответила ли касса хоть раз) — второе нужно пачке, чтобы
    отличать «касса жива» от «её не спрашивали» при подсчёте сбоев связи подряд.
    """
    now = timezone.now()

    # Касса — внешний вызов, его нельзя держать внутри транзакции с блокировкой
    # строки: ответ занимает сотни миллисекунд, а заказ всё это время был бы
    # заблокирован для вебхука. Спрашиваем до транзакции, состояние перепроверяем
    # внутри неё. Спрашиваем по КАЖДОМУ живому платежу: у заказа их может быть
    # несколько (повторная попытка после отказа банка), и оплатить можно любой.
    payments = list(
        Payment.objects.filter(order_id=order_id, status__in=_LIVE_PAYMENT).order_by("id")
    )
    paid: list[tuple[Payment, int | None]] = []
    unknown = in_flight = outage = answered = False
    for payment in payments:
        try:
            verdict, code = _ask_provider(payment)
        except Exception as exc:
            if _is_outage(exc):
                logger.warning(
                    "Заказ %s: касса недоступна (%s), отмену откладываем до следующего прогона",
                    order_id,
                    exc,
                )
                outage = True
                break
            # Ошибка именно по этому платежу. Отменять заказ, не зная, оплачен ли он,
            # нельзя; error — чтобы «вечный» заказ заметили люди, а не только лог.
            logger.exception(
                "Заказ %s: касса не ответила по платежу %s — отмену не делаем, "
                "заказ нужно разобрать вручную",
                order_id,
                payment.pk,
            )
            unknown = True
            continue
        answered = True
        if verdict == _PAID:
            paid.append((payment, code))
        elif verdict == _UNKNOWN:
            logger.warning(
                "Заказ %s: касса вернула непонятный статус %s по платежу %s, отмену откладываем",
                order_id,
                code,
                payment.pk,
            )
            unknown = True
        elif verdict == _IN_FLIGHT:
            in_flight = True

    # «Оплачен» важнее всего остального: ни непонятный ответ, ни сбой связи по
    # другому платежу не должны мешать применить оплату, которая уже прошла.
    if paid:
        _apply_paid(order_id, paid)
        return _SKIPPED, answered
    if outage:
        return _PROVIDER_FAILED, answered
    if unknown:
        return _SKIPPED, answered

    if in_flight:
        reserved_until = (
            Order.objects.filter(pk=order_id).values_list("reserved_until", flat=True).first()
        )
        if reserved_until is not None and now < reserved_until + in_flight_grace():
            # Покупатель в банке: вводит код, ждёт ответа. Отменить заказ сейчас —
            # гарантированно получить «деньги списаны, заказ отменён». Ждём, но не
            # вечно: зависший у кассы статус заказ держать не должен.
            logger.info("Заказ %s: оплата в процессе, отмену откладываем", order_id)
            return _SKIPPED, answered

    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(
                pk=order_id,
                payment_method=ONLINE_PAYMENT_METHOD,
                payment_status=OrderPaymentStatus.PENDING,
                reserved_until__lt=now,
            )
            # Доставку ещё считает менеджер: оплатить такой заказ нельзя, значит и
            # «не оплачен вовремя» к нему неприменимо (DRF-2736).
            .exclude(delivery_calc_status=DeliveryCalcStatus.MANUAL_REQUIRED)
            .first()
        )
        if order is None:
            # Оплатили, отменили или продлили резерв, пока мы ходили в кассу.
            return _SKIPPED, answered

        succeeded = Payment.objects.filter(
            order_id=order.pk,
            status__in=(PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED),
        ).exists()
        if succeeded:
            # Платёж уже зачтён, а заказ «ожидает оплаты»: статус заказа затёрт
            # (например, сохранением карточки в админке поверх только что пришедшей
            # оплаты). Отменять такой заказ нельзя — деньги получены. Чиним статус;
            # события оплаты были изданы, когда платёж стал успешным.
            order.payment_status = OrderPaymentStatus.PAID
            order.save(update_fields=["payment_status", "updated_at"])
            logger.error(
                "Заказ %s: платёж получен, а заказ числился неоплаченным — статус исправлен, "
                "отмена не выполнена",
                order.order_number,
            )
            return _SKIPPED, answered

        if order.fulfillment_status not in CANCELLABLE_BY_TIMEOUT:
            # Заказ уже в работе у склада — робот его не отменяет. Резерв заказа при
            # этом снимет общий janitor по сроку: наличие подтверждает менеджер.
            logger.warning(
                "Заказ %s просрочен по оплате, но статус %s — отмену решает менеджер",
                order.order_number,
                order.fulfillment_status,
            )
            return _SKIPPED, answered

        old_status = order.fulfillment_status
        order.payment_status = OrderPaymentStatus.EXPIRED
        order.fulfillment_status = FulfillmentStatus.CANCELLED
        order.save(update_fields=["payment_status", "fulfillment_status", "updated_at"])

        # Резерв снимаем В ТОЙ ЖЕ транзакции: «отменённый заказ с удержанным
        # резервом» не должен существовать ни мгновения. release_reservation
        # идемпотентен, двойного возврата остатков не будет, даже если janitor
        # заказов успел раньше.
        release_reservation(order.pk)

        # Покупатель должен узнать об отмене: страница оплаты у кассы всё ещё
        # открыта, и без уведомления он оплатит уже отменённый заказ.
        transaction.on_commit(lambda oid=order.pk, old=old_status: _notify_cancelled(oid, old))

    logger.info("Заказ %s отменён: оплата не поступила в срок", order.order_number)
    if order.sync_1c_status == Sync1CStatus.EXPORTED:
        # Обратного канала «заказ отменён» в контракте с 1С нет (см. orders/fulfillment).
        logger.warning(
            "Заказ %s отменён по таймауту ПОСЛЕ выгрузки в 1С — снять там вручную",
            order.order_number,
        )
    return _CANCELLED, answered


def expire_one(order_id: int) -> bool:
    """Истечь один онлайн-заказ. Атомарно и идемпотентно.

    True — заказ отменён здесь. False — отменять нечего или нельзя (уже оплачен,
    уже отменён, покупатель ещё платит, касса не ответила).
    """
    return _expire(order_id)[0] == _CANCELLED


def expire_unpaid_online_orders(limit: int = 500) -> int:
    """Отменить онлайн-заказы, у которых истёк резерв, а оплата не пришла."""
    now = timezone.now()
    ids = list(
        Order.objects.filter(
            payment_method=ONLINE_PAYMENT_METHOD,
            payment_status=OrderPaymentStatus.PENDING,
            reserved_until__lt=now,
        )
        .exclude(fulfillment_status=FulfillmentStatus.CANCELLED)
        .exclude(delivery_calc_status=DeliveryCalcStatus.MANUAL_REQUIRED)
        .order_by("reserved_until")
        .values_list("pk", flat=True)[:limit]
    )
    expired = 0
    failures = 0
    for order_id in ids:
        try:
            outcome, answered = _expire(order_id)
        except Exception:
            # Сбой на одном заказе (дедлок, ошибка подписчика) не должен лишить
            # остальных ни отмены, ни применения потерянной оплаты.
            logger.exception(
                "expire_unpaid_online_orders: заказ %s пропущен из-за ошибки", order_id
            )
            continue
        if outcome == _PROVIDER_FAILED:
            failures += 1
            if failures >= _MAX_PROVIDER_FAILURES:
                logger.warning(
                    "expire_unpaid_online_orders: касса не отвечает (%s сбоя подряд), "
                    "прогон прерван — продолжим в следующий раз",
                    failures,
                )
                break
            continue
        if answered:
            failures = 0  # касса жива; заказы без платежей о ней ничего не говорят
        if outcome == _CANCELLED:
            expired += 1
    if expired:
        logger.info("expire_unpaid_online_orders: отменено заказов — %s", expired)
    return expired
