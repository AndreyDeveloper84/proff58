"""Тест HTML-счёта (#324)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import CustomerType, Profile
from apps.catalog.models import Product, ProductStatus

User = get_user_model()


@pytest.mark.django_db
def test_b2b_invoice_html():
    user = User.objects.create_user(
        phone="+79007777777",
        password="pass",
        customer_type=CustomerType.B2B,
        full_name="Директор",
        email="buh@test.ru",
    )
    Profile.objects.create(
        user=user,
        company_name='ООО "Тест"',
        inn="7701234567",
        kpp="770101001",
        legal_address="г. Пенза, ул. Мира, 1",
    )
    product = Product.objects.create(
        name="Дрель",
        slug="inv-drel",
        price=Decimal("5000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=10,
        available_quantity=10,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    client.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    create = client.post("/api/orders/", {}, format="json")
    assert create.status_code == 201
    number = create.json()["order_number"]

    resp = client.get(f"/api/orders/{number}/invoice/")
    assert resp.status_code == 200
    assert "text/html" in resp["Content-Type"]
    content = resp.content.decode()
    assert "7701234567" in content
    assert number in content


@pytest.mark.django_db
def test_b2c_invoice_rejected():
    user = User.objects.create_user(phone="+79008888888", password="pass")
    product = Product.objects.create(
        name="Пила",
        slug="inv-pila",
        price=Decimal("3000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=5,
        available_quantity=5,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    create = client.post("/api/orders/", {}, format="json")
    number = create.json()["order_number"]

    resp = client.get(f"/api/orders/{number}/invoice/")
    assert resp.status_code == 400


REQUISITES = {
    "company_name": 'ООО "ПРОФЕССИОНАЛ"',
    "inn": "5835117632",
    "kpp": "583501001",
    "ogrn": "1165835058685",
    "address": "440062, г. Пенза, ул. 1-й Онежский проезд, 12",
    "bank_name": "КУРСКОЕ ОТДЕЛЕНИЕ N8596 ПАО СБЕРБАНК",
    "bank_bik": "043807606",
    "bank_account": "40702810048000002806",
    "bank_corr_account": "30101810300000000606",
    "director": "А.Г. Шатров",
}


def _b2b_invoice_html(phone: str, slug: str) -> str:
    """Пройти путь B2B-покупателя до счёта и вернуть его разметку."""
    user = User.objects.create_user(
        phone=phone,
        password="pass",
        customer_type=CustomerType.B2B,
        full_name="Директор",
        email="buh@test.ru",
    )
    Profile.objects.create(
        user=user,
        company_name='ООО "Покупатель"',
        inn="7701234567",
        kpp="770101001",
        legal_address="г. Пенза, ул. Мира, 1",
    )
    product = Product.objects.create(
        name="Перфоратор",
        slug=slug,
        price=Decimal("12000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=5,
        available_quantity=5,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    number = client.post("/api/orders/", {}, format="json").json()["order_number"]
    return client.get(f"/api/orders/{number}/invoice/").content.decode()


@pytest.mark.django_db
def test_счёт_содержит_банковские_реквизиты():
    """Без расчётного счёта и БИК платёжное поручение не заполнить."""
    from apps.core.models import SiteSettings

    settings = SiteSettings.get_solo()
    settings.requisites = REQUISITES
    settings.save(update_fields=["requisites"])

    html = _b2b_invoice_html("+79007777701", "inv-perf-1")

    assert "40702810048000002806" in html  # расчётный счёт
    assert "043807606" in html  # БИК
    assert "30101810300000000606" in html  # корсчёт
    assert "КУРСКОЕ ОТДЕЛЕНИЕ N8596 ПАО СБЕРБАНК" in html
    assert "5835117632" in html  # ИНН поставщика
    assert "583501001" in html  # КПП поставщика
    assert "А.Г. Шатров" in html  # подпись руководителя


@pytest.mark.django_db
def test_ставка_ндс_указана_явно():
    """«Без НДС» — тоже обязательный реквизит: молчание бухгалтерия не примет."""
    from apps.core.models import SiteSettings

    settings = SiteSettings.get_solo()
    settings.requisites = REQUISITES
    settings.save(update_fields=["requisites"])

    html = _b2b_invoice_html("+79007777702", "inv-perf-2")

    assert "Без НДС" in html or "В том числе НДС" in html


@pytest.mark.django_db
def test_без_заполненных_реквизитов_счёт_не_падает():
    """Реквизиты ещё не внесли — документ выходит без банковской части, но открывается."""
    from apps.core.models import SiteSettings

    settings = SiteSettings.get_solo()
    settings.requisites = {}
    settings.save(update_fields=["requisites"])

    html = _b2b_invoice_html("+79007777703", "inv-perf-3")

    assert "Покупатель" in html
    assert "Банк получателя" not in html
