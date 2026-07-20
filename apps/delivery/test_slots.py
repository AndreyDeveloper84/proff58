"""Тесты слотов доставки (#569): constraints, витрина available_slots, API.

Занятость и бронирование при оформлении заказа — в
apps/orders/tests/test_delivery_slots.py (там есть корзина/товары).
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.delivery.models import DeliverySlot, DeliveryType, DeliveryZone
from apps.delivery.slots import available_slots


@pytest.fixture(autouse=True)
def _clean_slots(db):
    DeliverySlot.objects.all().delete()
    yield
    DeliverySlot.objects.all().delete()


def _slot(days_ahead=1, **kw):
    defaults = dict(
        date=timezone.localdate() + timedelta(days=days_ahead),
        starts_at=time(10, 0),
        ends_at=time(14, 0),
        delivery_method=DeliveryType.COURIER,
        capacity=4,
        is_active=True,
    )
    defaults.update(kw)
    return DeliverySlot.objects.create(**defaults)


# ── constraints ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_ends_must_be_after_starts():
    # Вложенный atomic: IntegrityError не должен ломать транзакцию теста.
    with pytest.raises(IntegrityError), transaction.atomic():
        _slot(starts_at=time(14, 0), ends_at=time(10, 0))


@pytest.mark.django_db
def test_duplicate_window_rejected():
    _slot()
    with pytest.raises(IntegrityError), transaction.atomic():
        _slot()  # то же окно/метод/зона (zone=NULL, nulls_distinct=False)


# ── available_slots ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_excludes_inactive():
    _slot(is_active=False)
    assert available_slots() == []


@pytest.mark.django_db
def test_excludes_past_dates():
    _slot(days_ahead=-1)
    assert available_slots() == []


@pytest.mark.django_db
def test_excludes_today_already_started():
    now = timezone.localtime()
    started = (now - timedelta(hours=1)).time()
    if started > now.time():  # полночная граница — интервал «вчера», тест не о ней
        pytest.skip("слишком близко к полуночи")
    _slot(days_ahead=0, starts_at=started, ends_at=time(23, 59))
    assert available_slots() == []


@pytest.mark.django_db
def test_excludes_beyond_horizon(settings):
    settings.DELIVERY_SLOT_HORIZON_DAYS = 7
    _slot(days_ahead=8)
    inside = _slot(days_ahead=3)
    assert [s.pk for s in available_slots()] == [inside.pk]


@pytest.mark.django_db
def test_excludes_other_delivery_method():
    _slot(delivery_method=DeliveryType.PICKUP)
    assert available_slots() == []  # по умолчанию витрина courier


@pytest.mark.django_db
def test_zone_scoping():
    zone = DeliveryZone.objects.create(name="Пенза", slug="slot-city")
    zonal = _slot(zone=zone)
    global_slot = _slot(starts_at=time(15, 0), ends_at=time(18, 0))  # zone=NULL — всем

    for_city = {s.pk for s in available_slots(zone_slug="slot-city")}
    assert for_city == {zonal.pk, global_slot.pk}

    for_other = {s.pk for s in available_slots(zone_slug="slot-other")}
    assert for_other == {global_slot.pk}


@pytest.mark.django_db
def test_ordering_by_date_then_time():
    later = _slot(days_ahead=2)
    early = _slot(days_ahead=1, starts_at=time(15, 0), ends_at=time(18, 0))
    earliest = _slot(days_ahead=1)
    assert [s.pk for s in available_slots()] == [earliest.pk, early.pk, later.pk]


# ── API ────────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.mark.django_db
def test_api_slots_format(api_client):
    slot = _slot()
    resp = api_client.get("/api/delivery/slots/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slots"] == [
        {
            "id": slot.pk,
            "date": slot.date.isoformat(),
            "starts_at": "10:00",
            "ends_at": "14:00",
        }
    ]


@pytest.mark.django_db
def test_api_slots_empty(api_client):
    resp = api_client.get("/api/delivery/slots/")
    assert resp.status_code == 200
    assert resp.json() == {"slots": []}
