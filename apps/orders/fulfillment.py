"""Движение заказа по оси обработки руками менеджера.

До этого перевод статуса из админки был просто присваиванием поля: матрица
`transitions.py` соблюдалась только обменом с 1С и жизненным циклом счёта, а
побочные эффекты (возврат резерва при отмене, доменное событие) не наступали
вовсе. Здесь — единственная точка для менеджерского перехода, повторяющая
контракт `sync_1c.use_cases.confirm_orders`:

* переход проверяется матрицей (forward-only, отмена из любого нетерминального);
* повтор того же статуса — no-op без события;
* отмена возвращает резерв склада: «отменённый заказ с удержанным резервом»
  невозможен;
* `order_status_changed` издаётся после коммита — на него подписаны CRM и
  MAX-бот, то есть покупатель узнаёт о смене статуса.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core import events

from .models import FulfillmentStatus, Order, PaymentStatus, Sync1CStatus
from .transitions import allowed_transitions, can_transition

logger = logging.getLogger(__name__)


def next_steps(order: Order) -> list[tuple[str, str]]:
    """Куда менеджер может перевести заказ: [(значение, человеческая подпись)].

    Порядок — как в бизнес-цепочке, отмена всегда последней: это не «шаг
    вперёд», и в интерфейсе её место не рядом с остальными.
    """
    labels = dict(FulfillmentStatus.choices)
    targets = allowed_transitions(order.fulfillment_status)
    order_of_flow = [
        FulfillmentStatus.CONFIRMED,
        FulfillmentStatus.ASSEMBLING,
        FulfillmentStatus.READY,
        FulfillmentStatus.SHIPPED,
        FulfillmentStatus.COMPLETED,
        FulfillmentStatus.CANCELLED,
    ]
    return [(value, str(labels[value])) for value in order_of_flow if value in targets]


def advance_fulfillment(order_id: int, target: str, *, actor_id: int | None = None) -> Order:
    """Перевести обработку заказа в ``target``.

    Возвращает заказ. Поднимает ValidationError с человеческим текстом, если
    переход недопустим, — сообщение показывается менеджеру как есть.
    """
    labels = dict(FulfillmentStatus.choices)
    if target not in labels:
        raise ValidationError(f"Неизвестный статус обработки: {target}")

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        old_status = order.fulfillment_status

        if old_status == target:
            return order  # идемпотентный повтор: ни события, ни записи

        if not can_transition(old_status, target):
            targets = allowed_transitions(old_status)
            allowed = ", ".join(sorted(str(labels[t]) for t in targets))
            tail = f" Допустимо: {allowed}." if allowed else " Это конечный статус."
            raise ValidationError(
                f"Из статуса «{labels[old_status]}» нельзя перевести "
                f"в «{labels[target]}».{tail}"
            )

        order.fulfillment_status = target
        order.save(update_fields=["fulfillment_status", "updated_at"])

        # Возврат резерва В ТОЙ ЖЕ транзакции, как в invoice_lifecycle: иначе
        # между сохранением и коммитом существует отменённый заказ с удержанным
        # остатком. Идемпотентно (HELD→RELEASED), двойного возврата нет.
        if target == FulfillmentStatus.CANCELLED:
            from .reservation import release_reservation

            release_reservation(order.pk)

        transaction.on_commit(
            lambda oid=order.pk, o=old_status, n=target: events.order_status_changed.send(
                sender=Order, order_id=oid, old_status=o, new_status=n
            )
        )

    logger.info(
        "Заказ #%s: обработка %s → %s (менеджер id=%s)",
        order.order_number,
        old_status,
        target,
        actor_id,
    )
    return order


# Отмена покупателем разрешена, пока склад ещё не начал собирать заказ. Со
# «Собирается» и дальше товар уже снят с полок, и отмена — разговор с менеджером.
CUSTOMER_CANCELLABLE = frozenset({FulfillmentStatus.NEW, FulfillmentStatus.CONFIRMED})

# Оплаченный заказ покупатель не отменяет сам: автовозврата денег у нас нет, и
# «отменено» без возврата оставило бы человека без товара и без денег.
_PAID_STATUSES = frozenset({PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED})


def can_customer_cancel(order: Order) -> bool:
    """Виден ли покупателю смысл в кнопке отмены (для сериализатора и интерфейса).

    Ответ «да» не заменяет проверку в ``cancel_by_customer``: между отрисовкой
    страницы и нажатием статус мог уйти вперёд.
    """
    return (
        order.fulfillment_status in CUSTOMER_CANCELLABLE
        and order.payment_status not in _PAID_STATUSES
    )


def cancel_by_customer(order_id: int, *, actor_id: int | None = None) -> Order:
    """Отменить заказ по просьбе самого покупателя.

    Правило (решение владельца от 03.08.2026): можно, пока обработка в «Новый»
    или «Подтверждён»; неоплаченный. Матрицу переходов и побочные эффекты не
    дублируем — ими занимается ``advance_fulfillment``: возврат резерва в той же
    транзакции и ``order_status_changed`` после коммита.

    Проверка политики идёт под тем же блокирующим чтением, что и сам переход:
    иначе между «можно» и «перевожу» менеджер успел бы сдвинуть статус, и
    покупатель отменил бы уже собираемый заказ.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)

        if order.fulfillment_status == FulfillmentStatus.CANCELLED:
            return order  # повторное нажатие — не ошибка

        if order.payment_status in _PAID_STATUSES:
            raise ValidationError(
                "Заказ уже оплачен — отменить его может только менеджер: "
                "нужно оформить возврат денег. Позвоните нам, мы всё сделаем."
            )

        if order.fulfillment_status not in CUSTOMER_CANCELLABLE:
            labels = dict(FulfillmentStatus.choices)
            raise ValidationError(
                f"Заказ уже в статусе «{labels[order.fulfillment_status]}» — "
                "отменить его самостоятельно нельзя. Свяжитесь с менеджером."
            )

        cancelled = advance_fulfillment(order_id, FulfillmentStatus.CANCELLED, actor_id=actor_id)

    # 1С забирает только незавершённые заказы (export_new_orders исключает
    # отменённые), поэтому невыгруженный заказ до неё просто не доедет. А вот
    # уже выгруженный там останется: обратного канала «заказ отменён» в контракте
    # нет, и менеджеру придётся сказать об этом руками — пишем в лог заметно.
    if cancelled.sync_1c_status == Sync1CStatus.EXPORTED:
        logger.warning(
            "Заказ #%s отменён покупателем ПОСЛЕ выгрузки в 1С — снять там вручную",
            cancelled.order_number,
        )

    logger.info("Заказ #%s отменён покупателем (user id=%s)", cancelled.order_number, actor_id)
    return cancelled
