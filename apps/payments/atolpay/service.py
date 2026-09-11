"""Оплата через АТОЛ Pay: регистрация платежа, callback, возврат.

Как это устроено со стороны кассы:

1. Регистрируем платёж (``POST /payments``) и получаем ``paymentUrl`` — туда уходит
   покупатель. Своего идентификатора касса не выдаёт: платёж всюду адресуется
   нашим ``orderId``, поэтому он хранится в ``Payment.provider_order_id``.
2. Касса зовёт ``notificationUrl`` на каждое событие (оплата, отмена, возврат,
   фискализация). **Подписи у callback нет**, поэтому доверяем не телу запроса, а
   ответу ``GET /payments/{orderId}/status`` — как и в ЮKassa-ветке, состояние
   строится только по проверенному статусу.
3. Возврат и отмена — одна ручка ``/cancel``; что именно произошло, касса решает
   сама (в день оплаты — отмена без комиссии, позже — возврат).

Повторная попытка оплаты после отказа банка (статус 3 «повтор невозможен») требует
нового ``orderId`` — иначе касса ответит ``PAYMENT_EXISTS``. Поэтому у заказа может
быть несколько платежей, и номер для кассы получает суффикс попытки.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from apps.orders.models import Order

from .. import transitions
from ..models import Payment, PaymentMethod, PaymentProvider, PaymentStatus
from .client import AtolPayError, cancel_payment, payment_status, register_payment, to_kopecks
from .receipt import build_receipt

logger = logging.getLogger(__name__)

#: Числовой статус кассы → наш статус платежа (Таблица 9 документации).
#: 2 (банк не ответил), 10 (3-D Secure) и 12 (ошибка с возможностью повтора)
#: оставляют платёж в ожидании: деньги не списаны, покупатель может попробовать ещё.
PROVIDER_STATUS = {
    0: PaymentStatus.PENDING,  # в обработке
    1: PaymentStatus.SUCCEEDED,  # выполнен
    2: PaymentStatus.PENDING,  # банк не ответил
    3: PaymentStatus.CANCELED,  # ошибка, повтор невозможен
    4: PaymentStatus.CANCELED,  # отменён (после оплаты трактуется как возврат)
    5: PaymentStatus.REFUNDED,
    6: PaymentStatus.CANCELED,  # подозрение в мошенничестве
    7: PaymentStatus.PARTIALLY_REFUNDED,
    8: PaymentStatus.PARTIALLY_REFUNDED,
    9: PaymentStatus.CANCELED,  # платёж просрочен
    10: PaymentStatus.PENDING,  # подтверждение 3ds
    11: PaymentStatus.WAITING_CAPTURE,  # ожидает списания (двухстадийный)
    12: PaymentStatus.PENDING,  # ошибка, повтор возможен
}

#: Статусы, при которых деньги уже были получены и «отмена» означает возврат
#: (для уже возвращённого — повтор того же уведомления, касса их ретраит).
_MONEY_RECEIVED = {
    PaymentStatus.SUCCEEDED,
    PaymentStatus.PARTIALLY_REFUNDED,
    PaymentStatus.REFUNDED,
}

#: Платёж ещё можно оплатить по старой ссылке.
_LIVE_STATUSES = (PaymentStatus.PENDING, PaymentStatus.WAITING_CAPTURE)

#: Максимум попыток подобрать свободный orderId, если касса знает такой заказ.
_MAX_ORDER_ID_ATTEMPTS = 5


def site_url() -> str:
    """Публичный адрес витрины — база для returnUrl/notificationUrl."""
    configured = getattr(settings, "SITE_URL", "")
    if configured:
        return configured.rstrip("/")
    allowed = getattr(settings, "ALLOWED_HOSTS", [])
    host = next(
        (h for h in allowed if h not in ("*", "localhost", "127.0.0.1", "web")), "localhost"
    )
    return f"https://{host}"


def ascii_order_id(order_number: str, attempt: int = 1) -> str:
    """Номер заказа в виде, который принимает касса.

    Наши номера начинаются с кириллической «П» (``П-20260907-ABC123``), а АТОЛ
    допускает в ``orderId`` только латиницу, цифры и ``:+-_.`` — поэтому кириллица
    транслитерируется, а всё непонятное заменяется дефисом. Суффикс попытки нужен
    для повторной оплаты: тот же ``orderId`` касса второй раз не примет.
    """
    table = str.maketrans({"П": "P", "О": "O", "З": "Z", "К": "K", "С": "S", "Т": "T"})
    cleaned = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in ":+-_.")) else "-"
        for ch in order_number.translate(table)
    )
    suffix = "" if attempt <= 1 else f"-{attempt}"
    # 36 символов — лимит Альфа-Банка (у Т-Банка 255): держимся строгого.
    return f"{cleaned[: 36 - len(suffix)]}{suffix}"


def notification_url() -> str:
    """Адрес callback с секретом в query — единственный признак «свой» у АТОЛ."""
    url = f"{site_url()}{reverse('payments:atolpay-callback')}"
    token = getattr(settings, "ATOLPAY_CALLBACK_TOKEN", "")
    if not token:
        logger.warning(
            "ATOLPAY_CALLBACK_TOKEN пуст: callback кассы будет отвергнут — задайте секрет"
        )
        return url
    return f"{url}?t={token}"


def _existing_live_payment(order: Order) -> Payment | None:
    """Незакрытый платёж заказа — по нему покупателя ведём той же ссылкой."""
    return (
        Payment.objects.filter(
            order=order,
            provider=PaymentProvider.ATOLPAY,
            status__in=_LIVE_STATUSES,
        )
        .exclude(confirmation_url="")
        .order_by("-id")
        .first()
    )


def create_payment(order: Order, return_url: str = "") -> Payment:
    """Зарегистрировать платёж и вернуть его со ссылкой на платёжную форму."""
    existing = _existing_live_payment(order)
    if existing is not None:
        return existing

    amount = to_kopecks(order.total)
    if amount <= 0:
        raise ValueError(f"Заказ {order.order_number}: нулевая сумма, оплачивать нечего")

    if not return_url:
        return_url = f"{site_url()}/order/{order.order_number}/thanks"

    receipt = build_receipt(order)
    attempt = Payment.objects.filter(order=order, provider=PaymentProvider.ATOLPAY).count() + 1

    for _ in range(_MAX_ORDER_ID_ATTEMPTS):
        order_id = ascii_order_id(order.order_number, attempt)
        body: dict = {
            "amount": amount,
            "orderId": order_id,
            "sessionType": getattr(settings, "ATOLPAY_SESSION_TYPE", "oneStep"),
            "additionalProps": {
                "returnUrl": return_url,
                "notificationUrl": notification_url(),
            },
        }
        if receipt is not None:
            body["receipt"] = receipt
        if order.user_id:
            # Позволяет кассе привязать сохранённые карты к покупателю.
            body["buyerId"] = str(order.user_id)

        try:
            result = register_payment(body)
        except AtolPayError as exc:
            if exc.code == "PAYMENT_EXISTS":
                # Такой orderId касса уже знает (наш платёж не сохранился или
                # попытка повторяется) — берём следующий номер попытки.
                logger.warning("АТОЛ Pay: orderId %s занят, пробуем следующий", order_id)
                attempt += 1
                continue
            raise

        payment_url = result.get("paymentUrl", "")
        payment = Payment.objects.create(
            order=order,
            provider=PaymentProvider.ATOLPAY,
            provider_order_id=order_id,
            # У кассы нет собственного id платежа: и /status, и /cancel адресуются
            # тем же orderId, что мы отправили. Поэтому берём наш, а не эхо ответа —
            # иначе повторная попытка ловит конфликт уникальности.
            provider_payment_id=order_id,
            method=PaymentMethod.ATOLPAY,
            status=PaymentStatus.PENDING,
            amount=order.total,
            currency=order.currency,
            confirmation_url=payment_url,
            idempotency_key=f"atolpay-{order_id}",
        )
        logger.info(
            "АТОЛ Pay: платёж %s зарегистрирован для заказа %s на %s %s",
            order_id,
            order.order_number,
            order.total,
            order.currency,
        )
        return payment

    raise AtolPayError(
        code="PAYMENT_EXISTS", message=f"не удалось подобрать orderId для {order.order_number}"
    )


def provider_says_paid(payment: Payment) -> bool:
    """Спросить кассу напрямую: деньги пришли? Ошибка запроса — «не знаем»."""
    if not payment.provider_order_id:
        return False
    data = payment_status(payment.provider_order_id)
    return PROVIDER_STATUS.get(_status_code(data)) == PaymentStatus.SUCCEEDED


def _status_code(data: dict) -> int:
    """Числовой статус из ответа ``/status`` (ответ приходит и плоским, и в data)."""
    raw = data.get("status")
    if isinstance(raw, dict):  # на всякий случай: вложенный конверт
        raw = raw.get("status")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def _payload_status(payload: dict) -> int:
    """Числовой статус из тела уведомления. Используется только без верификации."""
    raw = str(payload.get("paymentStatus", "")).strip()
    return int(raw) if raw.lstrip("-").isdigit() else -1


def _target_status(code: int, current: str) -> str | None:
    """Целевой статус платежа с поправкой на то, получены ли уже деньги.

    «Отменён» (4) до оплаты — несостоявшийся платёж, после оплаты — возврат денег
    покупателю. Без этой поправки возврат из ЛК кассы выглядел бы как отмена и
    молча отбрасывался матрицей переходов.
    """
    target = PROVIDER_STATUS.get(code)
    if target == PaymentStatus.CANCELED and current in _MONEY_RECEIVED:
        return PaymentStatus.REFUNDED
    return target


def _apply_fiscal(payment: Payment, payload: dict) -> None:
    """Callback фискализации: чек пробит или нет. Деньги это не трогает."""
    payment.receipt_id = str(payload.get("receiptId", ""))[:64]
    payment.receipt_status = str(payload.get("status", ""))[:16]
    payment.receipt_error = str(payload.get("errorMessage", ""))
    payment.webhook_payload = payload
    payment.save(
        update_fields=[
            "receipt_id",
            "receipt_status",
            "receipt_error",
            "webhook_payload",
            "updated_at",
        ]
    )
    if payment.receipt_status != "success":
        # Транзакция при этом остаётся проведённой (док, раздел Callback): деньги
        # получены, а чек не пробит — это случай для менеджера, а не для отмены.
        logger.error(
            "АТОЛ Pay: чек по заказу %s не пробит (%s: %s) — требуется ручная фискализация",
            payment.order.order_number,
            payload.get("errorCode", ""),
            payment.receipt_error,
        )


def handle_callback(payload: dict, *, verify: bool = True) -> None:
    """Обработать уведомление кассы. Идемпотентно; ошибка → 5xx и повтор кассой.

    Проверочный запрос к кассе делается ДО транзакции. Касса шлёт уведомления
    об оплате и о чеке подряд, с разницей в секунды; если держать строку платежа
    под блокировкой на время сетевого вызова, второе уведомление стоит в очереди
    столько, сколько отвечает касса (на стенде — до 16 с при 3–5 без очереди), и
    при медленной кассе упирается в таймаут воркера. Ответ кассы — факт о
    платеже, он не зависит от нашей блокировки, поэтому его безопасно получить
    заранее; состояние перепроверяется уже внутри транзакции.
    """
    order_id = str(payload.get("orderId", ""))
    if not order_id:
        logger.warning("АТОЛ Pay callback без orderId")
        return

    if not Payment.objects.filter(
        provider=PaymentProvider.ATOLPAY, provider_order_id=order_id
    ).exists():
        logger.warning("АТОЛ Pay callback по неизвестному платежу %s", order_id)
        return

    if payload.get("type") == "fiscal":
        _handle_fiscal_callback(order_id, payload)
        return

    # Состояние строим по проверенному статусу кассы, тело callback — только аудит:
    # подписи у него нет, и поддельный «оплачено» иначе пометил бы заказ оплаченным.
    code = _payload_status(payload)
    started = time.monotonic()
    if verify:
        try:
            code = _status_code(payment_status(order_id))
        except AtolPayError as exc:
            logger.error("АТОЛ Pay: статус платежа %s не подтверждён (%s)", order_id, exc.code)
            raise
    verified_at = time.monotonic()

    _apply_payment_callback(order_id, payload, code)
    # Разбивка по фазам — чтобы медленный callback было видно, где именно медленный:
    # ответ кассы (сеть/банк) или наша транзакция (блокировка, подписчики событий).
    logger.info(
        "АТОЛ Pay callback %s type=%s status=%s: проверка %.2fс, переход %.2fс",
        order_id,
        payload.get("type"),
        code,
        verified_at - started,
        time.monotonic() - verified_at,
    )


def _locked_payment(order_id: str) -> Payment | None:
    return (
        Payment.objects.select_for_update()
        .filter(provider=PaymentProvider.ATOLPAY, provider_order_id=order_id)
        .first()
    )


@transaction.atomic
def _handle_fiscal_callback(order_id: str, payload: dict) -> None:
    payment = _locked_payment(order_id)
    if payment is not None:
        _apply_fiscal(payment, payload)


@transaction.atomic
def _apply_payment_callback(order_id: str, payload: dict, code: int) -> None:
    """Перевести платёж по уже проверенному статусу кассы. Строка — под блокировкой."""
    payment = _locked_payment(order_id)
    if payment is None:
        return

    payment.webhook_payload = payload
    target = _target_status(code, payment.status)

    if target is None:
        logger.info("АТОЛ Pay: статус %s платежа %s без обработки", code, order_id)
        payment.save(update_fields=["webhook_payload", "updated_at"])
        return

    if payment.status == target and target not in (PaymentStatus.PARTIALLY_REFUNDED,):
        payment.save(update_fields=["webhook_payload", "updated_at"])
        return

    if not transitions.is_allowed(payment.status, target):
        logger.warning(
            "АТОЛ Pay: переход %s → %s для %s запрещён, уведомление проигнорировано",
            payment.status,
            target,
            order_id,
        )
        payment.save(update_fields=["webhook_payload", "updated_at"])
        return

    if target == PaymentStatus.SUCCEEDED:
        _check_amount(payment, payload)
        transitions.apply_succeeded(payment, reference=order_id, extra_fields=["webhook_payload"])
    elif target == PaymentStatus.CANCELED:
        reason = str(payload.get("errorMessage") or payload.get("errorCode") or "не оплачен")
        transitions.apply_canceled(
            payment, reason=reason, reference=order_id, extra_fields=["webhook_payload"]
        )
    elif target in (PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED):
        full = target == PaymentStatus.REFUNDED
        transitions.apply_refunded(
            payment,
            refund_amount=_callback_amount(payload) or (payment.amount if full else Decimal("0")),
            full=full,
            reference=order_id,
            extra_fields=["webhook_payload"],
        )
    elif target == PaymentStatus.WAITING_CAPTURE:
        transitions.apply_waiting_capture(payment, extra_fields=["webhook_payload"])


def _callback_amount(payload: dict) -> Decimal | None:
    """Сумма из callback (копейки) в рублях, если она пришла."""
    raw = payload.get("amount")
    if raw is None:
        return None
    try:
        return Decimal(str(raw)) / 100
    except (ArithmeticError, ValueError):
        return None


def _check_amount(payment: Payment, payload: dict) -> None:
    """Сверить сумму из callback с суммой платежа — деньги должны совпасть до копейки."""
    amount = _callback_amount(payload)
    if amount is None:
        return
    if to_kopecks(amount) != to_kopecks(payment.amount):
        logger.error(
            "АТОЛ Pay: сумма платежа %s не совпала — касса %s, заказ %s",
            payment.provider_order_id,
            amount,
            payment.amount,
        )
        raise ValueError("Payment amount mismatch")


def cancel_or_refund(payment: Payment, amount: Decimal | None = None) -> dict:
    """Вернуть деньги покупателю. Отмена это или возврат — решает касса."""
    if not payment.provider_order_id:
        raise ValueError("У платежа нет номера заказа в кассе")
    kopecks = None if amount is None else to_kopecks(amount)
    return cancel_payment(payment.provider_order_id, kopecks)
