"""Заказ из админки не удаляется (DRF-2300).

Заказ — история продажи: от него каскадом уходят платежи, чеки и отзыв, по
номеру его знает 1С. Памятка запрещала удаление словами, а кнопка была.
Теперь запрет серверный: одиночное удаление, массовое `delete_selected` и
прямой POST по `…/delete/` отклоняются для сотрудника с выданным правом и для
суперпользователя. Отмена заказа при этом работает и снимает резерв один раз.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse

from apps.catalog.models import Product, ProductStatus
from apps.orders.admin import OrderAdmin
from apps.orders.models import FulfillmentStatus, Order, OrderItem, ReservationStatus
from apps.payments.models import Payment

User = get_user_model()


@pytest.fixture
def суперпользователь(db):
    return User.objects.create_superuser(phone="+79993330001", password="pwd12345")


@pytest.fixture
def сотрудник_с_правом_удаления(db):
    """Обычный staff, которому явно выдали `delete_order` — самый сильный не-superuser."""
    user = User.objects.create_user(phone="+79993330002", password="pwd12345", is_staff=True)
    codenames = ("view_order", "change_order", "delete_order")
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


@pytest.fixture(params=["суперпользователь", "сотрудник_с_правом_удаления"])
def актор(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def товар(db):
    return Product.objects.create(
        name="Товар",
        code_1c="del-1",
        slug="del-1",
        unit="шт",
        price=Decimal("100.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("7"),
        reserved_quantity=Decimal("3"),
    )


@pytest.fixture
def заказ(db, товар):
    order = Order.objects.create(
        order_number="DEL-1",
        fulfillment_status=FulfillmentStatus.NEW,
        total=Decimal("300.00"),
        customer_phone="+79001112233",
        reservation_status=ReservationStatus.HELD,
    )
    OrderItem.objects.create(
        order=order,
        product=товар,
        quantity=3,
        price_final=Decimal("100.00"),
        line_total=Decimal("300.00"),
    )
    Payment.objects.create(order=order, amount=Decimal("300.00"))
    return order


def _всё_на_месте(заказ, товар):
    """Заказ, строки и платёж целы, резерв не тронут (pre_delete DRF-1002 не срабатывал)."""
    assert Order.objects.filter(pk=заказ.pk).exists()
    assert OrderItem.objects.filter(order=заказ).count() == 1
    assert Payment.objects.filter(order=заказ).count() == 1
    товар.refresh_from_db()
    assert товар.available_quantity == Decimal("7")
    assert товар.reserved_quantity == Decimal("3")


def test_в_карточке_нет_ссылки_удалить(client, актор, заказ):
    client.force_login(актор)
    page = client.get(reverse("admin:orders_order_change", args=[заказ.pk])).content.decode()
    assert reverse("admin:orders_order_delete", args=[заказ.pk]) not in page


def test_в_списке_нет_действия_delete_selected(актор):
    request = RequestFactory().get("/")
    request.user = актор
    actions = OrderAdmin(Order, AdminSite()).get_actions(request)
    assert "delete_selected" not in actions


@pytest.mark.parametrize("метод", ["get", "post"])
def test_прямой_запрос_на_delete_url_отклоняется(client, актор, заказ, товар, метод):
    client.force_login(актор)
    url = reverse("admin:orders_order_delete", args=[заказ.pk])
    response = getattr(client, метод)(url, {"post": "yes"} if метод == "post" else None)
    assert response.status_code == 403
    _всё_на_месте(заказ, товар)


@pytest.mark.parametrize("данные", [{"index": "0"}, {}, {"select_across": "1"}])
def test_массовое_удаление_из_списка_ничего_не_удаляет(client, актор, заказ, товар, данные):
    client.force_login(актор)
    response = client.post(
        reverse("admin:orders_order_changelist"),
        {"action": "delete_selected", "_selected_action": [str(заказ.pk)], **данные},
    )
    # У OrderAdmin своих действий нет: без delete_selected список действий пуст,
    # Django не обрабатывает POST как действие и просто показывает список (200).
    # Главное — не 403-ловушка с побочным эффектом, а нетронутая БД ниже.
    assert response.status_code == 200
    _всё_на_месте(заказ, товар)


def test_отмена_через_кнопку_работает_и_снимает_резерв_один_раз(
    client, суперпользователь, заказ, товар
):
    client.force_login(суперпользователь)
    url = reverse("admin:orders_order_advance", args=[заказ.pk, FulfillmentStatus.CANCELLED])

    client.post(url)
    заказ.refresh_from_db()
    товар.refresh_from_db()
    assert заказ.fulfillment_status == FulfillmentStatus.CANCELLED
    assert товар.available_quantity == Decimal("10")  # 7 + 3
    assert товар.reserved_quantity == Decimal("0")

    client.post(url)  # повторная отмена — остаток не двигается второй раз
    товар.refresh_from_db()
    assert товар.available_quantity == Decimal("10")
    assert товар.reserved_quantity == Decimal("0")
    assert Order.objects.filter(pk=заказ.pk).exists()
