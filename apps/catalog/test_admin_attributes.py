"""Smoke-тесты админки характеристик: раздел «Значения» + доработка «Характеристики»."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    Source,
)

User = get_user_model()


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_superuser(phone="+79990000077", password="pw")
    c = Client()
    c.force_login(admin)
    return c


@pytest.fixture
def voltage(db):
    cat = Category.add_root(name="Электроинструмент", slug="elektro")
    attr = Attribute.objects.create(
        slug="voltage",
        name="Напряжение",
        attribute_type=AttributeType.DECIMAL,
        unit="В",
        is_filterable=True,
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_filter=True)
    return cat, attr


@pytest.mark.django_db
def test_value_changelist_loads(admin_client, voltage):
    cat, attr = voltage
    p = Product.objects.create(name="Дрель 18В", code_1c="v1", slug="v1", category=cat)
    ProductAttributeValue.objects.create(
        product=p, attribute=attr, value_decimal=Decimal("18"), source=Source.REGEX, confidence=100
    )
    resp = admin_client.get("/admin/catalog/productattributevalue/")
    assert resp.status_code == 200
    assert b"18" in resp.content  # читаемое значение в колонке


@pytest.mark.django_db
def test_value_confidence_filter(admin_client, voltage):
    resp = admin_client.get("/admin/catalog/productattributevalue/?confidence_band=low")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_attribute_changelist_shows_counts(admin_client, voltage):
    cat, attr = voltage
    p = Product.objects.create(name="Дрель", code_1c="a1", slug="a1", category=cat)
    ProductAttributeValue.objects.create(
        product=p, attribute=attr, value_decimal=Decimal("18"), source=Source.REGEX
    )
    resp = admin_client.get("/admin/catalog/attribute/")
    assert resp.status_code == 200
    assert "Электроинструмент".encode() in resp.content  # колонка «Категории»


@pytest.mark.django_db
def test_manual_edit_sets_source_manual(admin_client, voltage):
    """Ручная правка значения в админке → source=manual, confidence=100."""
    cat, attr = voltage
    p = Product.objects.create(name="Дрель 18В", code_1c="m1", slug="m1", category=cat)
    pav = ProductAttributeValue.objects.create(
        product=p, attribute=attr, value_decimal=Decimal("18"), source=Source.REGEX, confidence=100
    )
    resp = admin_client.post(
        f"/admin/catalog/productattributevalue/{pav.pk}/change/",
        {
            "product": str(p.pk),
            "attribute": str(attr.pk),
            "value_text": "",
            "value_integer": "",
            "value_decimal": "20",  # менеджер исправил 18 → 20
            "value_boolean": "unknown",
            "value_option": "",
        },
    )
    assert resp.status_code in (200, 302)
    pav.refresh_from_db()
    assert pav.value_decimal == Decimal("20")
    assert pav.source == Source.MANUAL  # источник переведён в ручной
    assert pav.confidence == 100
