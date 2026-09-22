"""Подписчики доменных событий заказов (#423, B-03).

При оплате резерв списывается (confirm), при отмене платежа — освобождается
(release). Читаем закоммиченные данные по order_id из payload. На новый заказ —
письмо сотрудникам через outbox уведомлений (DRF-2296).

Отдельно — `pre_delete` на самом заказе (DRF-1002): резерв обязан сниматься на
уровне модели, а не конкретного вызова, иначе удаление мимо `release_reservation`
оставляет остаток занятым навсегда.
"""

from __future__ import annotations

import logging

from django.db.models.signals import pre_delete

from apps.core import events

from .models import Order
from .reservation import confirm_reservation, release_reservation

logger = logging.getLogger(__name__)


def _on_payment_succeeded(sender, *, order_id, payment_id=None, **kwargs):
    # Оплата подтверждена → резерв списываем (товар уходит). Идемпотентно.
    confirm_reservation(order_id)


def _on_payment_failed(sender, *, order_id, payment_id=None, reason="", **kwargs):
    # Платёж отменён/просрочен → возвращаем резерв в свободный остаток. Идемпотентно.
    release_reservation(order_id)


def staff_notify_snapshot(order_id: int) -> dict | None:
    """Снимок заказа для письма сотрудникам (DRF-2296): только то, что и так
    видно в админке; без токенов и id пользователя. None — заказа нет."""
    from django.utils import timezone

    from apps.notifications.services import admin_url

    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return None
    customer = order.customer_name or "—"
    if order.company_name:
        customer = f"{customer} ({order.company_name}, ИНН {order.inn or '—'})"
    delivery = order.delivery_method or "—"
    if order.delivery_address:
        delivery = f"{delivery}, {order.delivery_address}"
    total = f"{order.total:.2f}"
    if order.delivery_calc_status == "manual_required":
        # DRF-2299: менеджер — первый, кто должен увидеть, что доставку надо посчитать.
        delivery = f"{delivery} — СТОИМОСТЬ ТРЕБУЕТ РАСЧЁТА"
        total = f"{total} (предварительно, без доставки)"
    return {
        "order_number": order.order_number,
        "created_at": timezone.localtime(order.created_at).strftime("%d.%m.%Y %H:%M"),
        "customer": customer,
        "customer_phone": order.customer_phone or "—",
        "total": total,
        "currency": order.currency,
        "items_count": order.items.count(),
        "delivery": delivery,
        "payment": order.get_payment_method_display() if order.payment_method else "—",
        "admin_url": admin_url(f"/admin/orders/order/{order.pk}/change/"),
    }


def _on_order_created_notify_staff(sender, *, order_id, **kwargs):
    """Письмо сотрудникам о новом заказе. Любой сбой (брокер недоступен, ошибка
    сборки снимка) только логируется: заказ уже закоммичен, ответ покупателю
    не должен стать 500 из-за уведомления."""
    try:
        payload = staff_notify_snapshot(order_id)
        if payload is None:
            return
        from apps.notifications.services import notify_staff

        notify_staff(
            event="staff_order_created",
            payload=payload,
            idempotency_key=f"staff-order-created-{order_id}",
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой уведомления сотрудников о заказе %s", order_id)


def _on_order_pre_delete(sender, instance, **kwargs):
    """Удаляют заказ — возвращаем удержанный остаток (DRF-1002).

    Ловит любой путь удаления: админка, shell, каскад. Сигнал сам отключает
    fast-delete (Django загрузит объекты и разошлёт сигналы вместо одного DELETE),
    а строки заказа на момент pre_delete ещё в базе — резерв есть что вернуть.
    Идемпотентно: для RELEASED/CONFIRMED вызов ничего не делает.
    """
    release_reservation(instance.pk)


def connect() -> None:
    events.payment_succeeded.connect(
        _on_payment_succeeded, dispatch_uid="orders_confirm_reservation"
    )
    events.payment_failed.connect(_on_payment_failed, dispatch_uid="orders_release_reservation")
    events.order_created.connect(
        _on_order_created_notify_staff, dispatch_uid="orders_notify_staff_order_created"
    )
    pre_delete.connect(
        _on_order_pre_delete, sender=Order, dispatch_uid="orders_release_reservation_on_delete"
    )
