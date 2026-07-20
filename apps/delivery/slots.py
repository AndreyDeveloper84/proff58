"""Витрина и валидация слотов доставки (#569).

``available_slots`` — активные будущие слоты со свободными местами в горизонте
``DELIVERY_SLOT_HORIZON_DAYS``. ``lock_slot_for_booking`` — авторитетная
проверка при оформлении: блокирует строку слота (``select_for_update``) и
валидирует всё, кроме вместимости — её проверяет вызывающий (orders), потому
что занятость считается по заказам (``apps.orders.slots``, function-level
импорт — зеркально тому, как orders вызывает delivery в ``place_order``).

Даты/время сравниваются в таймзоне проекта через ``timezone.localdate()`` /
``timezone.localtime()``: контейнеры живут в UTC, и ``date.today()`` около
полуночи ошибается на смещение таймзоны.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import DeliverySlot, DeliveryType


def _horizon_days() -> int:
    return int(getattr(settings, "DELIVERY_SLOT_HORIZON_DAYS", 14))


def _future_q(now) -> Q:
    """Слот «в будущем»: дата впереди либо сегодня, но интервал ещё не начался."""
    today = timezone.localdate(now)
    return Q(date__gt=today) | Q(date=today, starts_at__gt=timezone.localtime(now).time())


def slot_snapshot(slot: DeliverySlot) -> dict:
    """Снимок слота для заказа: история не ломается при правке слота админом."""
    return {
        "slot_id": slot.pk,
        "date": slot.date.isoformat(),
        "starts_at": slot.starts_at.strftime("%H:%M"),
        "ends_at": slot.ends_at.strftime("%H:%M"),
        "delivery_method": slot.delivery_method,
        "zone": slot.zone.slug if slot.zone_id else "",
    }


def available_slots(
    *,
    method: str = DeliveryType.COURIER,
    zone_slug: str = "",
    now=None,
) -> list[DeliverySlot]:
    """Слоты, которые можно предложить покупателю. Полные исключаются."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    qs = (
        DeliverySlot.objects.filter(
            is_active=True,
            delivery_method=method,
            date__lte=today + timedelta(days=_horizon_days()),
        )
        .filter(_future_q(now))
        .filter(Q(zone__isnull=True) | Q(zone__slug=zone_slug))
        .select_related("zone")
        .order_by("date", "starts_at")
    )
    slots = list(qs)
    if not slots:
        return []
    from apps.orders.slots import occupied_counts

    occupied = occupied_counts([s.pk for s in slots])
    return [s for s in slots if occupied.get(s.pk, 0) < s.capacity]


def lock_slot_for_booking(
    slot_id: int,
    *,
    method: str,
    zone_slug: str = "",
    now=None,
) -> DeliverySlot:
    """Заблокировать слот и проверить его пригодность для бронирования.

    Вызывать строго внутри transaction.atomic. Вместимость проверяет
    вызывающий под этим же локом.
    """
    now = now or timezone.now()
    try:
        # of=("self",): лочим только строку слота — FOR UPDATE не применим к
        # nullable-стороне outer join (LEFT JOIN на zone из select_related).
        slot = (
            DeliverySlot.objects.select_for_update(of=("self",))
            .select_related("zone")
            .get(pk=slot_id)
        )
    except DeliverySlot.DoesNotExist:
        raise ValidationError("Слот доставки не найден — выберите другой интервал.") from None
    if not slot.is_active:
        raise ValidationError("Слот доставки недоступен — выберите другой интервал.")
    today = timezone.localdate(now)
    if slot.date < today or (
        slot.date == today and slot.starts_at <= timezone.localtime(now).time()
    ):
        raise ValidationError("Слот доставки уже прошёл — выберите другой интервал.")
    if slot.delivery_method != method:
        raise ValidationError("Слот не подходит для выбранного способа доставки.")
    if slot.zone_id and slot.zone.slug != zone_slug:
        raise ValidationError("Слот не действует в выбранной зоне доставки.")
    return slot
