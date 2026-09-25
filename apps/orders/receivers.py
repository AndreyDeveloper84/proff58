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
from decimal import Decimal

from django.db.models.signals import pre_delete

from apps.core import events

from .models import Order
from .reservation import confirm_reservation, release_reservation

logger = logging.getLogger(__name__)
_ZERO = Decimal("0.00")


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


def _customer_email(order) -> str:
    email = (order.customer_email or "").strip()
    if not email and order.user_id:
        email = (order.user.email or "").strip()
    return email


def _order_url_line(order) -> str:
    """Ссылка на страницу заказа: ЛК для зарегистрированных, гостям — без токена
    (токен доступа в письмо не кладём). Пустой SITE_URL → строки нет."""
    from django.conf import settings

    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not base:
        return ""
    if order.user_id:
        return f"Заказ в личном кабинете:\n{base}/account/orders/{order.order_number}\n"
    return f"Страница заказа:\n{base}/order/{order.order_number}/thanks\n"


def customer_order_snapshot(order) -> dict:
    """Снимок заказа для письма покупателю (T2): номер, состав, известные суммы и
    состояние доставки. При manual_required стоимость доставки не показывается
    как 0 — пишем, что её уточнит менеджер, а итог помечаем предварительным."""
    from django.utils import timezone

    items = list(order.items.all())
    lines = [
        f"— {it.name} × {it.quantity} {it.unit or 'шт'} = {it.line_total:.2f} {order.currency}"
        for it in items
    ]
    goods_total = sum((it.line_total for it in items), _ZERO)
    discount = order.items_discount_total or _ZERO
    if discount > _ZERO:
        lines.append(f"Скидка по акциям: −{discount:.2f} {order.currency}")
        goods_total = max(goods_total - discount, _ZERO)

    delivery = order.delivery_method or "—"
    if order.delivery_address:
        delivery = f"{delivery}, {order.delivery_address}"
    if order.delivery_calc_status == "manual_required":
        delivery_line = "стоимость уточнит менеджер"
        total_line = f"{order.total:.2f} {order.currency} (предварительно, без доставки)"
    elif order.delivery_calc_status == "not_required":
        delivery_line = "не требуется"
        total_line = f"{order.total:.2f} {order.currency}"
    else:
        cost = order.delivery_cost or _ZERO
        delivery_line = "бесплатно" if cost == _ZERO else f"{cost:.2f} {order.currency}"
        total_line = f"{order.total:.2f} {order.currency}"

    name = (order.customer_name or "").strip()
    return {
        "order_number": order.order_number,
        "name_note": f", {name}" if name else "",
        "created_at": timezone.localtime(order.created_at).strftime("%d.%m.%Y %H:%M"),
        "items": "\n".join(lines) or "—",
        "goods_total": f"{goods_total:.2f}",
        "currency": order.currency,
        "delivery_line": delivery_line,
        "total_line": total_line,
        "delivery": delivery,
        "payment": order.get_payment_method_display() if order.payment_method else "—",
        "order_url_line": _order_url_line(order),
    }


def _on_order_created_notify_customer(sender, *, order_id, **kwargs):
    """Письмо покупателю о принятом заказе (T2). Нет e-mail — письма нет;
    любой сбой только логируется, заказ уже закоммичен."""
    try:
        order = Order.objects.filter(pk=order_id).select_related("user").first()
        if order is None:
            return
        email = _customer_email(order)
        if not email:
            return
        from apps.notifications.services import notify_customer

        notify_customer(
            email=email,
            event="customer_order_created",
            payload=customer_order_snapshot(order),
            idempotency_key=f"customer-order-created-{order_id}",
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой письма покупателю о заказе %s", order_id)


# Переходы обработки, о которых пишем покупателю (тот же whitelist, что у MAX —
# apps/integration_max/receivers.py). Новых статусов не вводим.
_STATUS_EMAIL = {
    "confirmed": ("заказ подтверждён", "Заказ №{n} подтверждён. Мы начали сборку."),
    "ready": ("заказ собран", "Заказ №{n} собран.{note}"),
    "shipped": ("заказ передан в доставку", "Заказ №{n} передан в доставку.{note}"),
    "completed": ("заказ доставлен", "Заказ №{n} доставлен. Спасибо за покупку!"),
    "cancelled": ("заказ отменён", "Заказ №{n} отменён."),
}


def _on_order_status_changed_notify_customer(sender, *, order_id, old_status, new_status, **kw):
    meta = _STATUS_EMAIL.get(new_status)
    if meta is None:
        return
    try:
        order = Order.objects.filter(pk=order_id).select_related("user").first()
        if order is None:
            return
        email = _customer_email(order)
        if not email:
            return
        title, text = meta
        note = ""
        if new_status == "ready":
            from apps.delivery.models import DeliveryType

            note = (
                " Готов к выдаче в пункте самовывоза."
                if order.delivery_method == DeliveryType.PICKUP
                else " Скоро передадим в доставку."
            )
        elif new_status == "shipped" and order.tracking_number:
            note = f" Трек-номер: {order.tracking_number}."
        from apps.notifications.services import notify_customer

        notify_customer(
            email=email,
            event="customer_order_status_changed",
            payload={
                "order_number": order.order_number,
                "status_title": title,
                "status_text": text.format(n=order.order_number, note=note),
                "order_url_line": _order_url_line(order),
            },
            idempotency_key=f"customer-order-status-{order_id}-{new_status}",
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой письма покупателю о статусе заказа %s", order_id)


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
    events.order_created.connect(
        _on_order_created_notify_customer, dispatch_uid="orders_notify_customer_order_created"
    )
    events.order_status_changed.connect(
        _on_order_status_changed_notify_customer,
        dispatch_uid="orders_notify_customer_order_status_changed",
    )
    pre_delete.connect(
        _on_order_pre_delete, sender=Order, dispatch_uid="orders_release_reservation_on_delete"
    )
