"""Бронирование слота доставки при оформлении заказа (#569).

Слот — только B2C + курьер; сервер перепроверяет всё сам (не доверяя фронту):
существование, активность, «не в прошлом», совместимость метода/зоны и
вместимость. Гонка за последнее место закрыта select_for_update на строке
слота; отмена заказа освобождает место автоматически (занятость = COUNT живых
заказов, см. apps.orders.slots).
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.delivery.models import DeliverySlot, DeliveryType, DeliveryZone
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.services import add_to_cart, place_order
from apps.orders.slots import occupied_count


@pytest.fixture
def courier_zone(db):
    return DeliveryZone.objects.create(slug="slot-penza", name="Пенза", price=Decimal("300"))


@pytest.fixture
def slot(db):
    return DeliverySlot.objects.create(
        date=timezone.localdate() + timedelta(days=1),
        starts_at=time(10, 0),
        ends_at=time(14, 0),
        capacity=4,
    )


def _guest():
    return {"customer_name": "Гость", "customer_phone": "+79001234567"}


def _b2b():
    return {
        "customer_name": "Иван Петров",
        "customer_phone": "+79001234567",
        "customer_email": "buh@romashka.ru",
        "customer_type": "b2b",
        "company_name": "ООО «Ромашка»",
        "inn": "7700000000",
        "kpp": "770001001",
        "legal_address": "г. Пенза, ул. Ленина, 1",
    }


def _courier_delivery(slot_id, zone="slot-penza"):
    return {
        "delivery_method": "courier",
        "delivery_zone": zone,
        "delivery_slot_id": slot_id,
    }


def _place(cart, product, delivery, qty=1, customer_data=None):
    add_to_cart(cart, product, qty)
    return place_order(cart, customer_data=customer_data or _guest(), delivery=delivery)


# ── happy path ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_slot_saved_with_snapshot(cart, product, slot, courier_zone):
    order = _place(cart, product, _courier_delivery(slot.pk))
    assert order.delivery_slot_id == slot.pk
    snap = order.delivery_slot_snapshot
    assert snap["slot_id"] == slot.pk
    assert snap["date"] == slot.date.isoformat()
    assert snap["starts_at"] == "10:00"
    assert snap["ends_at"] == "14:00"
    assert snap["zone"] == ""  # глобальный слот
    assert occupied_count(slot.pk) == 1


@pytest.mark.django_db
def test_slot_optional(cart, product, slot, courier_zone):
    """Пустой справочник/невыбранный слот не блокируют курьерский заказ."""
    order = _place(cart, product, {"delivery_method": "courier", "delivery_zone": "slot-penza"})
    assert order.delivery_slot_id is None
    assert order.delivery_slot_snapshot == {}


# ── валидации ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_unknown_slot_rejected(cart, product, courier_zone):
    with pytest.raises(ValidationError, match="не найден"):
        _place(cart, product, _courier_delivery(999999))


@pytest.mark.django_db
def test_inactive_slot_rejected(cart, product, slot, courier_zone):
    slot.is_active = False
    slot.save(update_fields=["is_active"])
    with pytest.raises(ValidationError, match="недоступен"):
        _place(cart, product, _courier_delivery(slot.pk))


@pytest.mark.django_db
def test_past_slot_rejected(cart, product, slot, courier_zone):
    DeliverySlot.objects.filter(pk=slot.pk).update(date=timezone.localdate() - timedelta(days=1))
    with pytest.raises(ValidationError, match="уже прошёл"):
        _place(cart, product, _courier_delivery(slot.pk))


@pytest.mark.django_db
def test_pickup_with_slot_rejected(cart, product, slot):
    with pytest.raises(ValidationError, match="курьерской"):
        _place(
            cart,
            product,
            {"delivery_method": "pickup", "delivery_slot_id": slot.pk},
        )


@pytest.mark.django_db
def test_method_mismatch_rejected(cart, product, courier_zone):
    pickup_slot = DeliverySlot.objects.create(
        date=timezone.localdate() + timedelta(days=1),
        starts_at=time(10, 0),
        ends_at=time(14, 0),
        delivery_method=DeliveryType.PICKUP,
        capacity=4,
    )
    with pytest.raises(ValidationError, match="способа доставки"):
        _place(cart, product, _courier_delivery(pickup_slot.pk))


@pytest.mark.django_db
def test_foreign_zone_slot_rejected(cart, product, courier_zone):
    other = DeliveryZone.objects.create(slug="slot-region", name="Область", price=Decimal("500"))
    zonal = DeliverySlot.objects.create(
        date=timezone.localdate() + timedelta(days=1),
        starts_at=time(10, 0),
        ends_at=time(14, 0),
        zone=other,
        capacity=4,
    )
    with pytest.raises(ValidationError, match="зоне"):
        _place(cart, product, _courier_delivery(zonal.pk, zone="slot-penza"))


@pytest.mark.django_db
def test_b2b_with_slot_rejected(cart, product, slot):
    delivery = {"delivery_method": "pickup", "delivery_slot_id": slot.pk}
    with pytest.raises(ValidationError, match="юрлиц"):
        _place(cart, product, delivery, customer_data=_b2b())
    assert occupied_count(slot.pk) == 0


# ── вместимость и «гонка» ──────────────────────────────────────────────


@pytest.mark.django_db
def test_full_slot_rejected(cart, product, product2, slot, courier_zone):
    slot.capacity = 1
    slot.save(update_fields=["capacity"])

    _place(cart, product, _courier_delivery(slot.pk))
    assert occupied_count(slot.pk) == 1

    from apps.orders.models import Cart

    cart2 = Cart.objects.create(session_key="sess-slot-2")
    # Второй покупатель на последнее (уже занятое) место: сериализация на
    # select_for_update строки слота — конкурент увидит COUNT после коммита.
    with pytest.raises(ValidationError, match="занято"):
        _place(cart2, product2, _courier_delivery(slot.pk))


@pytest.mark.django_db
def test_cancelled_order_frees_slot(cart, product, product2, slot, courier_zone):
    slot.capacity = 1
    slot.save(update_fields=["capacity"])

    order = _place(cart, product, _courier_delivery(slot.pk))
    Order.objects.filter(pk=order.pk).update(fulfillment_status=FulfillmentStatus.CANCELLED)
    assert occupied_count(slot.pk) == 0

    from apps.delivery.slots import available_slots
    from apps.orders.models import Cart

    assert [s.pk for s in available_slots(zone_slug="slot-penza")] == [slot.pk]
    cart2 = Cart.objects.create(session_key="sess-slot-3")
    order2 = _place(cart2, product2, _courier_delivery(slot.pk))
    assert order2.delivery_slot_id == slot.pk


@pytest.mark.django_db
def test_full_slot_hidden_from_available(cart, product, slot, courier_zone):
    slot.capacity = 1
    slot.save(update_fields=["capacity"])
    _place(cart, product, _courier_delivery(slot.pk))

    from apps.delivery.slots import available_slots

    assert available_slots(zone_slug="slot-penza") == []


# ── API-контракт ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_api_order_with_slot(api, product, slot, courier_zone):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Иван",
            "customer_phone": "+79990000077",
            "delivery_method": "courier",
            "delivery_zone": "slot-penza",
            "delivery_slot_id": slot.pk,
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["delivery_slot"] == {
        "date": slot.date.isoformat(),
        "starts_at": "10:00",
        "ends_at": "14:00",
    }


@pytest.mark.django_db
def test_api_b2b_with_slot_rejected(api, b2b_user, product, slot):
    api.force_authenticate(user=b2b_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post("/api/orders/", {"delivery_slot_id": slot.pk}, format="json")
    assert resp.status_code == 400
    assert occupied_count(slot.pk) == 0


@pytest.mark.django_db
def test_api_pickup_with_slot_rejected(api, product, slot):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Иван",
            "customer_phone": "+79990000078",
            "delivery_method": "pickup",
            "delivery_slot_id": slot.pk,
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_api_order_without_slot_returns_null(api, product):
    """Старые/бесслотовые заказы отдают delivery_slot: null (guard пустого снимка)."""
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {"customer_name": "Иван", "customer_phone": "+79990000079"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["delivery_slot"] is None


@pytest.mark.django_db
def test_snapshot_survives_slot_deactivation(api, product, slot, courier_zone):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Иван",
            "customer_phone": "+79990000080",
            "delivery_method": "courier",
            "delivery_zone": "slot-penza",
            "delivery_slot_id": slot.pk,
        },
        format="json",
    )
    order_number = resp.json()["order_number"]
    token = resp.json()["access_token"]
    slot.is_active = False
    slot.save(update_fields=["is_active"])

    detail = api.get(f"/api/orders/{order_number}/guest/?t={token}")
    assert detail.status_code == 200
    assert detail.json()["delivery_slot"]["starts_at"] == "10:00"
