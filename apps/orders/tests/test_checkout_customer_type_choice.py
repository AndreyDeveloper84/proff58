"""Тип покупателя при оформлении — выбор на форме, а не тип учётной записи.

Вошедший под аккаунтом физлица выбирал «Организация», заполнял реквизиты и
получал «Оплата по счёту доступна только для B2B»: сервер брал тип из аккаунта.
Ценник единый (ADR-0013 §A.4), поэтому выбор на форме безопасен; аккаунт при
этом не меняется.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.orders.models import B2BInvoice, Order
from apps.orders.services import add_to_cart, place_order

B2B_FORM = {
    "customer_name": "Андрей",
    "customer_phone": "+79023530378",
    "customer_email": "andrey@example.com",
    "customer_type": "b2b",
    "company_name": "ООО Клевер",
    "inn": "5835117632",
    "kpp": "583501001",
    "legal_address": "Пензенская область, Пензенский район",
    "payment_method": "invoice",
    "delivery_method": "pickup",
}


@pytest.mark.django_db
def test_вошедшее_физлицо_может_оформить_заказ_на_организацию(api, b2c_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")

    resp = api.post("/api/orders/", B2B_FORM, format="json")

    assert resp.status_code == 201, resp.json()
    order = Order.objects.get(order_number=resp.json()["order_number"])
    assert order.customer_type == "b2b"
    assert order.company_name == "ООО Клевер" and order.inn == "5835117632"
    assert order.payment_method == "invoice"
    assert B2BInvoice.objects.filter(order=order).exists()
    b2c_user.refresh_from_db()
    assert b2c_user.customer_type == "b2c"  # аккаунт не меняется


@pytest.mark.django_db
def test_вошедшее_физлицо_без_выбора_остаётся_розницей(api, b2c_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Иван",
            "customer_phone": "+79990000010",
            "payment_method": "cash",
            "delivery_method": "pickup",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["customer_type"] == "b2c"


@pytest.mark.django_db
def test_юрлицо_может_оформить_розничный_заказ_по_выбору(api, b2b_user, product):
    api.force_authenticate(user=b2b_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Пётр",
            "customer_phone": "+79990000011",
            "customer_type": "b2c",
            "payment_method": "cash",
            "delivery_method": "pickup",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["customer_type"] == "b2c"
    assert resp.json()["payment_method"] == "cash"


@pytest.mark.django_db
def test_юрлицо_без_выбора_оформляет_как_организация(api, b2b_user, product):
    api.force_authenticate(user=b2b_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Пётр",
            "customer_phone": "+79990000011",
            "payment_method": "invoice",
            "delivery_method": "pickup",
            "legal_address": "г. Пенза, ул. Ленина, 1",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["customer_type"] == "b2b"


@pytest.mark.django_db
def test_сервис_уважает_выбор_на_форме(cart, product, b2c_user):
    add_to_cart(cart, product, 1)
    data = {k: v for k, v in B2B_FORM.items() if k not in ("payment_method", "delivery_method")}
    order = place_order(cart, user=b2c_user, customer_data=data, payment_method="invoice")
    assert order.customer_type == "b2b" and order.total == Decimal("1000.00")


@pytest.mark.django_db
def test_реквизиты_добираются_из_профиля_если_форма_пуста(api, b2c_user, product):
    from apps.accounts.models import Profile

    Profile.objects.update_or_create(
        user=b2c_user,
        defaults={
            "company_name": "ООО Профиль",
            "inn": "7700000000",
            "kpp": "770001001",
            "legal_address": "г. Пенза, ул. Мира, 5",
        },
    )
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Иван",
            "customer_phone": "+79990000010",
            "customer_type": "b2b",
            "payment_method": "invoice",
            "delivery_method": "pickup",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    order = Order.objects.get(order_number=resp.json()["order_number"])
    assert order.company_name == "ООО Профиль" and order.inn == "7700000000"


@pytest.mark.django_db
def test_мусорный_тип_покупателя_отклоняется(api, b2c_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = api.post(
        "/api/orders/",
        {**B2B_FORM, "customer_type": "vip"},
        format="json",
    )
    assert resp.status_code == 400 and "customer_type" in resp.json()
