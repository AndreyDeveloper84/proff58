"""#560: API счетов B2B в ЛК — owner-only список и детали."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.orders.invoice_lifecycle import expire_due_invoices
from apps.orders.models import B2BInvoice
from apps.orders.services import add_to_cart, place_order

User = get_user_model()


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


@pytest.fixture
def b2b_owner(db):
    return User.objects.create_user(phone="+79005550077", password="pass12345", customer_type="b2b")


@pytest.fixture
def b2b_order(cart, product, b2b_owner):
    add_to_cart(cart, product, 2)
    return place_order(cart, user=b2b_owner, customer_data=_b2b())


@pytest.mark.django_db
def test_invoice_list_owner_only_fields(api, b2b_owner, b2b_order):
    api.force_authenticate(user=b2b_owner)
    resp = api.get("/api/account/invoices/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    inv = data["results"][0]
    assert inv["number"] == f"СЧ-{b2b_order.order_number}"
    assert inv["status"] == "issued"
    assert inv["order_number"] == b2b_order.order_number
    assert inv["goods_total"] == "2000.00"  # 2 × 1000, доставки у B2B нет
    assert inv["total"] == "2000.00"
    assert Decimal(inv["vat_amount"]) > 0
    assert inv["is_expired"] is False
    assert inv["invoice_url"] == f"/api/orders/{b2b_order.order_number}/invoice/"
    assert inv["valid_until"] is not None


@pytest.mark.django_db
def test_invoice_list_not_leaking_to_others(api, b2b_order):
    stranger = User.objects.create_user(phone="+79005550078", password="pass12345")
    api.force_authenticate(user=stranger)
    resp = api.get("/api/account/invoices/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0

    resp = api.get(f"/api/account/invoices/СЧ-{b2b_order.order_number}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_invoice_list_requires_auth(api):
    assert api.get("/api/account/invoices/").status_code in (401, 403)


@pytest.mark.django_db
def test_invoice_detail(api, b2b_owner, b2b_order):
    api.force_authenticate(user=b2b_owner)
    resp = api.get(f"/api/account/invoices/СЧ-{b2b_order.order_number}/")
    assert resp.status_code == 200
    assert resp.json()["order_number"] == b2b_order.order_number


@pytest.mark.django_db
def test_expired_invoice_flagged(api, b2b_owner, b2b_order):
    """После janitor'а счёт отдаётся как expired + заказ отменён (для UI)."""
    past = timezone.now() - timezone.timedelta(minutes=1)
    B2BInvoice.objects.filter(order=b2b_order).update(valid_until=past)
    expire_due_invoices()

    api.force_authenticate(user=b2b_owner)
    inv = api.get("/api/account/invoices/").json()["results"][0]
    assert inv["status"] == "expired"
    assert inv["is_expired"] is True
    assert inv["payment_status"] == "expired"
    assert inv["fulfillment_status"] == "cancelled"


@pytest.mark.django_db
def test_overdue_but_not_yet_expired_flagged(api, b2b_owner, b2b_order):
    """Срок вышел, janitor ещё не добежал → is_expired уже True (честный UI)."""
    past = timezone.now() - timezone.timedelta(minutes=1)
    B2BInvoice.objects.filter(order=b2b_order).update(valid_until=past)

    api.force_authenticate(user=b2b_owner)
    inv = api.get("/api/account/invoices/").json()["results"][0]
    assert inv["status"] == "issued"
    assert inv["is_expired"] is True
