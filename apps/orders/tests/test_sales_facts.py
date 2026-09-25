"""Продажи сайта как источник рейтинга «хитов».

Проверяем, что продажей считается только реально отгруженное: на витрину не
должен попасть товар из заказа, который ещё могут отменить.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import ProductSalesFact, SalesSource
from apps.catalog.sales import sales_window
from apps.orders.models import FulfillmentStatus, Order, OrderItem, PaymentStatus
from apps.orders.services import sold_quantities
from apps.orders.tasks import publish_sales_facts

pytestmark = pytest.mark.django_db


def make_order(
    product,
    quantity: int = 1,
    *,
    fulfillment: str = FulfillmentStatus.COMPLETED,
    payment: str = PaymentStatus.PAID,
    days_ago: int = 0,
) -> Order:
    order = Order.objects.create(
        order_number=f"T-{Order.objects.count() + 1:05d}",
        fulfillment_status=fulfillment,
        payment_status=payment,
        customer_name="Тест",
        customer_phone="+79990000001",
        total=Decimal("1000.00"),
    )
    # created_at — auto_now_add, поэтому дату продажи сдвигаем явным update.
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    OrderItem.objects.create(
        order=order,
        product=product,
        name=product.name,
        price_final=Decimal("1000.00"),
        quantity=quantity,
        line_total=Decimal("1000.00") * quantity,
    )
    return order


class TestSoldQuantities:
    def test_считает_отгруженное_и_выполненное(self, product):
        make_order(product, 2, fulfillment=FulfillmentStatus.COMPLETED)
        make_order(product, 3, fulfillment=FulfillmentStatus.SHIPPED)

        since, until = sales_window()
        rows = sold_quantities(since, until)

        assert len(rows) == 1  # один товар, один день
        assert rows[0][0] == product.id
        assert rows[0][2] == Decimal("5")

    @pytest.mark.parametrize(
        "fulfillment",
        [
            FulfillmentStatus.NEW,
            FulfillmentStatus.CONFIRMED,
            FulfillmentStatus.ASSEMBLING,
            FulfillmentStatus.READY,
            FulfillmentStatus.CANCELLED,
        ],
    )
    def test_не_отгруженное_продажей_не_считается(self, product, fulfillment):
        make_order(product, 5, fulfillment=fulfillment)

        assert sold_quantities(*sales_window()) == []

    def test_возврат_снимает_продажу(self, product):
        make_order(product, 5, payment=PaymentStatus.REFUNDED)

        assert sold_quantities(*sales_window()) == []

    def test_продажи_вне_окна_не_попадают(self, product, settings):
        settings.SALES_WINDOW_DAYS = 30
        make_order(product, 5, days_ago=60)

        assert sold_quantities(*sales_window()) == []

    def test_строка_без_товара_пропускается(self, product):
        """Номенклатуру удалили — product обнулён, привязать продажу не к чему."""
        order = make_order(product, 5)
        OrderItem.objects.filter(order=order).update(product=None)

        assert sold_quantities(*sales_window()) == []


class TestPublishSalesFacts:
    def test_публикует_продажи_в_каталог(self, product):
        make_order(product, 4)

        result = publish_sales_facts()

        assert result["written"] == 1
        fact = ProductSalesFact.objects.get()
        assert fact.source == SalesSource.SITE
        assert fact.quantity == Decimal("4.000")

    def test_повторный_прогон_не_удваивает(self, product):
        make_order(product, 4)

        publish_sales_facts()
        publish_sales_facts()

        assert ProductSalesFact.objects.count() == 1
        assert ProductSalesFact.objects.get().quantity == Decimal("4.000")

    def test_отменённый_задним_числом_заказ_исчезает_из_статистики(self, product):
        order = make_order(product, 4)
        publish_sales_facts()
        assert ProductSalesFact.objects.exists()

        order.fulfillment_status = FulfillmentStatus.CANCELLED
        order.save(update_fields=["fulfillment_status"])
        publish_sales_facts()

        assert not ProductSalesFact.objects.exists()

    def test_не_трогает_выгрузку_1с(self, product):
        from apps.catalog.sales import SalesRow, record_sales_facts

        record_sales_facts(
            SalesSource.ONEC,
            [SalesRow(product.id, timezone.localdate(), Decimal("9"))],
        )

        publish_sales_facts()

        assert ProductSalesFact.objects.filter(source=SalesSource.ONEC).count() == 1
