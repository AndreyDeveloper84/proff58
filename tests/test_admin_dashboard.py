"""Стартовый экран админки «Сегодня».

Проверяем то, ради чего он сделан: человек видит очереди с числами, каждая
ссылка ведёт в отфильтрованный список, а пустые очереди внимание не занимают.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import Product, ProductStatus
from apps.orders.models import FulfillmentStatus, Order
from config.admin_site import build_today_groups

User = get_user_model()


@pytest.fixture
def админ(db):
    user = User.objects.create_superuser(phone="+79990000000", password="pwd12345")
    return user


def test_на_пустой_базе_очередей_нет(db):
    assert build_today_groups() == []


def test_новый_заказ_даёт_карточку_со_ссылкой_на_фильтр(db):
    Order.objects.create(
        order_number="T-1", fulfillment_status=FulfillmentStatus.NEW, total=Decimal("100.00")
    )

    groups = build_today_groups()
    orders = next(g for g in groups if g["title"] == "Заказы")
    card = next(c for c in orders["cards"] if c["label"].startswith("Новые"))

    assert card["count"] == 1
    assert card["url"] == "/admin/orders/order/?fulfillment_status__exact=new"


def test_товар_без_категории_попадает_в_очередь(db):
    Product.objects.create(
        name="Без категории", slug="bez-kategorii", code_1c="d-1", status=ProductStatus.IMPORTED
    )

    groups = build_today_groups()
    catalog = next(g for g in groups if g["title"] == "Товары")
    labels = {c["label"] for c in catalog["cards"]}

    assert "Требуют внимания" in labels
    assert "Без категории" in labels


def test_нулевые_карточки_не_показываются(db):
    """Ноль — не работа, и место на экране занимать не должен."""
    Order.objects.create(
        order_number="T-2", fulfillment_status=FulfillmentStatus.COMPLETED, total=Decimal("1.00")
    )

    for group in build_today_groups():
        for card in group["cards"]:
            assert card["count"] > 0


def test_страница_админки_отдаёт_дашборд(client, админ):
    client.force_login(админ)
    Order.objects.create(
        order_number="T-3", fulfillment_status=FulfillmentStatus.NEW, total=Decimal("100.00")
    )

    response = client.get("/admin/")

    assert response.status_code == 200
    assert "Что нужно сделать сегодня" in response.content.decode()
    assert "Новые — подтвердить" in response.content.decode()


def test_на_пустой_базе_страница_говорит_что_всё_разобрано(client, админ):
    client.force_login(админ)

    response = client.get("/admin/")

    assert "Всё разобрано" in response.content.decode()
