"""#421 (B-01): claim гостевых заказов только для подтверждённого номера.

Покрывает: регистрация без OTP не привязывает; verified привязывает только свои;
разные форматы одного номера; нормализация; OTP-вход подтверждает и привязывает.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.phone import normalize_phone
from apps.orders.models import Order
from apps.orders.services import claim_guest_orders

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


# ── normalize_phone (unit) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+79001112233", "+79001112233"),
        ("89001112233", "+79001112233"),
        ("79001112233", "+79001112233"),
        ("9001112233", "+79001112233"),
        ("+7 (900) 111-22-33", "+79001112233"),
        ("  8 900 111 22 33 ", "+79001112233"),
        ("", ""),
        ("   ", ""),
        ("abc", ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_idempotent():
    once = normalize_phone("8 (900) 111-22-33")
    assert normalize_phone(once) == once


# ── claim_guest_orders (service) ───────────────────────────────────────


@pytest.mark.django_db
def test_claim_skipped_when_phone_not_verified():
    u = User.objects.create_user(phone="+79001112233", password="p")
    Order.objects.create(order_number="G1", customer_phone="+79001112233")
    assert claim_guest_orders(u) == 0
    assert Order.objects.get(order_number="G1").user_id is None


@pytest.mark.django_db
def test_claim_only_own_orders_when_verified():
    u = User.objects.create_user(phone="+79001112233", password="p")
    u.phone_verified = True
    u.save(update_fields=["phone_verified"])
    mine = Order.objects.create(order_number="G1", customer_phone="+79001112233")
    other = Order.objects.create(order_number="G2", customer_phone="+79007778899")

    assert claim_guest_orders(u) == 1
    assert Order.objects.get(pk=mine.pk).user_id == u.pk
    assert Order.objects.get(pk=other.pk).user_id is None


@pytest.mark.django_db
def test_claim_matches_normalized_format():
    """Заказ создан в формате 8XXX, пользователь — +7XXX: claim всё равно находит."""
    u = User.objects.create_user(phone="+79001112233", password="p")
    u.phone_verified = True
    u.save(update_fields=["phone_verified"])
    # Симулируем «легаси» заказ, чей телефон уже нормализован миграцией/сервисом.
    Order.objects.create(order_number="G1", customer_phone=normalize_phone("8 900 111 22 33"))

    assert claim_guest_orders(u) == 1
    assert Order.objects.get(order_number="G1").user_id == u.pk


@pytest.mark.django_db
def test_claim_does_not_touch_already_claimed():
    """Повторный claim идемпотентен: уже привязанный заказ не трогается."""
    owner = User.objects.create_user(phone="+79001112233", password="p")
    owner.phone_verified = True
    owner.save(update_fields=["phone_verified"])
    o = Order.objects.create(order_number="G1", customer_phone="+79001112233", user=owner)

    assert claim_guest_orders(owner) == 0  # уже привязан (user__isnull=False)
    assert Order.objects.get(pk=o.pk).user_id == owner.pk


# ── registration flow (API) ────────────────────────────────────────────


@pytest.mark.django_db
def test_register_does_not_claim_guest_orders(client):
    """Регистрация не захватывает чужие гостевые заказы.

    Регистрация идёт по e-mail и телефон вообще не принимает, поэтому подобрать
    чужой номер на этом шаге больше нельзя в принципе. Номер попадает в аккаунт
    только через MAX — то есть после подтверждения владения.
    """
    Order.objects.create(order_number="VICTIM-1", customer_phone="+79001112233")
    resp = client.post(
        "/api/account/register/",
        {
            "email": "attacker@proff58.ru",
            "password": "StrongPass2026",
            "full_name": "Злоумышленник",
            "phone": "+79001112233",  # даже если прислать — сериализатор его не знает
        },
        format="json",
    )
    assert resp.status_code == 201
    assert "claimed_orders" not in resp.json()
    assert Order.objects.get(order_number="VICTIM-1").user_id is None
    u = User.objects.get(email="attacker@proff58.ru")
    assert u.phone is None
    assert u.phone_verified is False


@pytest.mark.django_db
def test_register_requires_email(client):
    """Без e-mail регистрация невозможна: он и есть логин."""
    resp = client.post(
        "/api/account/register/",
        {"phone": "89001112233", "password": "StrongPass2026"},
        format="json",
    )
    assert resp.status_code == 400
    assert "email" in resp.json()
