"""Доступные способы оплаты (DRF-948, DRF-951).

Правило простое, но за ним деньги: показать способ, которым магазин не принимает
оплату, — значит пообещать то, чего не будет. Сервер решает авторитетно, браузер
только рисует.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus
from apps.orders.payment_methods import PaymentMethod, available_payment_methods

pytestmark = pytest.mark.django_db


class TestПравилоДоступности:
    def test_самовывоз_физлица_три_способа(self):
        assert available_payment_methods("b2c", "pickup") == [
            "online",
            "cash",
            "card_on_pickup",
        ]

    # Оплату курьеру магазин не подтверждал: показывать её нельзя,
    # пока не будет подтверждённой бизнес-логики.
    def test_курьер_физлица_только_онлайн(self):
        assert available_payment_methods("b2c", "courier") == ["online"]

    def test_юрлицо_только_счёт(self):
        assert available_payment_methods("b2b", "pickup") == ["invoice"]
        assert available_payment_methods("b2b", "courier") == ["invoice"]


def make_product(slug: str) -> Product:
    return Product.objects.create(
        name="Дрель",
        slug=slug,
        price=Decimal("5000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=10,
        available_quantity=10,
    )


def order_payload(**kwargs) -> dict:
    base = {
        "customer_name": "Иван",
        "customer_phone": "+79001112233",
        "customer_email": "ivan@test.ru",
        "customer_type": "b2c",
        "delivery_method": "pickup",
    }
    return {**base, **kwargs}


class TestСерверПроверяетАвторитетно:
    def _client_with_cart(self, slug: str) -> APIClient:
        client = APIClient()
        product = make_product(slug)
        client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
        return client

    @pytest.mark.parametrize("method", ["online", "cash", "card_on_pickup"])
    def test_самовывоз_принимает_все_три(self, method):
        client = self._client_with_cart(f"pay-{method}")

        resp = client.post("/api/orders/", order_payload(payment_method=method), format="json")

        assert resp.status_code == 201, resp.data
        assert resp.json()["payment_method"] == method

    # Подмена в запросе не проходит: браузер мог показать что угодно.
    @pytest.mark.parametrize("method", ["cash", "card_on_pickup"])
    def test_курьеру_наличные_и_карта_отклоняются(self, method):
        client = self._client_with_cart(f"courier-{method}")

        resp = client.post(
            "/api/orders/",
            order_payload(
                payment_method=method,
                delivery_method="courier",
                delivery_address="г. Пенза, ул. Мира, 1",
            ),
            format="json",
        )

        assert resp.status_code == 400
        assert "payment_method" in resp.data

    def test_без_способа_оплаты_остаётся_онлайн(self):
        """Старые клиенты не присылают поле — контракт не ломаем."""
        client = self._client_with_cart("pay-default")

        resp = client.post("/api/orders/", order_payload(), format="json")

        assert resp.status_code == 201
        assert resp.json()["payment_method"] == PaymentMethod.ONLINE.value

    def test_физлицу_счёт_недоступен(self):
        client = self._client_with_cart("pay-invoice-b2c")

        resp = client.post("/api/orders/", order_payload(payment_method="invoice"), format="json")

        assert resp.status_code == 400
