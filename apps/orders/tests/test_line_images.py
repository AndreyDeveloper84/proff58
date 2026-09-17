"""Фото товара в корзине и в заказе.

До этого строка корзины и позиция заказа не несли картинку вовсе, а витрина
рисовала на её месте зашитую заглушку — даже у товаров с тремя фотографиями.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import ProductImage
from apps.orders.api.serializers import OrderSerializer
from apps.orders.models import FulfillmentStatus, Order, OrderItem, PaymentStatus


@pytest.mark.django_db
def test_строка_корзины_несёт_главное_фото(api, product, product2):
    ProductImage.objects.create(product=product, image="products/drel.jpg", is_main=True)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    api.post("/api/cart/items/", {"product_id": product2.id, "quantity": 1}, format="json")

    lines = {line["product_id"]: line for line in api.get("/api/cart/").json()["lines"]}

    assert lines[product.id]["image"] == "/media/products/drel.jpg"
    # У второго товара фото нет — None, а не выдуманный адрес: витрина покажет
    # «Фото готовится».
    assert lines[product2.id]["image"] is None


@pytest.mark.django_db
def test_фото_корзины_грузится_одним_запросом(api, product, product2):
    ProductImage.objects.create(product=product, image="products/a.jpg", is_main=True)
    ProductImage.objects.create(product=product2, image="products/b.jpg", is_main=True)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    one_line = len(_queries_for_cart(api))
    api.post("/api/cart/items/", {"product_id": product2.id, "quantity": 1}, format="json")
    two_lines = len(_queries_for_cart(api))

    # Вторая строка не должна добавлять запрос за своим фото.
    assert two_lines - one_line <= 1


def _queries_for_cart(api):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        api.get("/api/cart/")
    return [q for q in ctx.captured_queries if "catalog_productimage" in q["sql"]]


@pytest.mark.django_db
def test_позиция_заказа_несёт_фото(product, product2):
    ProductImage.objects.create(product=product, image="products/drel.jpg", is_main=True)
    order = Order.objects.create(
        order_number="T-IMG-1",
        fulfillment_status=FulfillmentStatus.NEW,
        payment_status=PaymentStatus.PENDING,
        customer_name="Тест",
        customer_phone="+79990000001",
        total=Decimal("1500.00"),
    )
    for p in (product, product2):
        OrderItem.objects.create(
            order=order, product=p, name=p.name, price_final=p.price, quantity=1, line_total=p.price
        )

    items = {i["product_id"]: i for i in OrderSerializer(order).data["items"]}

    assert items[product.id]["image"] == "/media/products/drel.jpg"
    assert items[product2.id]["image"] is None


@pytest.mark.django_db
def test_удалённый_товар_не_ломает_заказ(product):
    order = Order.objects.create(
        order_number="T-IMG-2",
        fulfillment_status=FulfillmentStatus.NEW,
        payment_status=PaymentStatus.PENDING,
        customer_name="Тест",
        customer_phone="+79990000001",
        total=Decimal("1000.00"),
    )
    OrderItem.objects.create(
        order=order,
        product=None,
        name="Снятый товар",
        price_final=Decimal("1000"),
        quantity=1,
        line_total=Decimal("1000"),
    )

    # Снимок заказа живёт дольше товара: фото нет, но заказ показывается.
    assert OrderSerializer(order).data["items"][0]["image"] is None
