"""Товар из админки не удаляется (DRF-2300).

Товар связан с 1С по `code_1c` и с историей заказов; удаление обрывает связи и
каскадом уносит фото, характеристики и записи обмена. Запрет серверный:
одиночное удаление, массовое `delete_selected` и прямой POST по `…/delete/`
отклоняются для сотрудника с выданным правом и для суперпользователя.
Снятие с витрины и возврат на проверку при этом работают.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Product, ProductStatus
from apps.orders.models import Order, OrderItem

User = get_user_model()


@pytest.fixture
def суперпользователь(db):
    return User.objects.create_superuser(phone="+79993330011", password="pwd12345")


@pytest.fixture
def сотрудник_с_правом_удаления(db):
    user = User.objects.create_user(phone="+79993330012", password="pwd12345", is_staff=True)
    codenames = ("view_product", "change_product", "delete_product")
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


@pytest.fixture(params=["суперпользователь", "сотрудник_с_правом_удаления"])
def актор(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def товар(db):
    return Product.objects.create(
        name="Дрель",
        code_1c="pdel-1",
        slug="pdel-1",
        unit="шт",
        price=Decimal("1000.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


@pytest.fixture
def строка_заказа(db, товар):
    order = Order.objects.create(order_number="PDEL-1", customer_phone="+79001112233")
    return OrderItem.objects.create(
        order=order,
        product=товар,
        quantity=1,
        price_final=Decimal("1000.00"),
        line_total=Decimal("1000.00"),
    )


def _всё_на_месте(товар, строка_заказа):
    assert Product.objects.filter(pk=товар.pk, code_1c="pdel-1").exists()
    строка_заказа.refresh_from_db()
    assert строка_заказа.product_id == товар.pk


def test_в_карточке_нет_ссылки_удалить(client, актор, товар):
    client.force_login(актор)
    page = client.get(reverse("admin:catalog_product_change", args=[товар.pk])).content.decode()
    assert reverse("admin:catalog_product_delete", args=[товар.pk]) not in page


def test_в_списке_нет_действия_delete_selected(актор):
    request = RequestFactory().get("/")
    request.user = актор
    actions = ProductAdmin(Product, AdminSite()).get_actions(request)
    assert "delete_selected" not in actions
    # Собственные действия списка на месте — запрет точечный.
    assert "action_needs_review" in actions


@pytest.mark.parametrize("метод", ["get", "post"])
def test_прямой_запрос_на_delete_url_отклоняется(client, актор, товар, строка_заказа, метод):
    client.force_login(актор)
    url = reverse("admin:catalog_product_delete", args=[товар.pk])
    response = getattr(client, метод)(url, {"post": "yes"} if метод == "post" else None)
    assert response.status_code == 403
    _всё_на_месте(товар, строка_заказа)


@pytest.mark.parametrize("данные", [{"index": "0"}, {}, {"select_across": "1"}])
def test_массовое_удаление_из_списка_ничего_не_удаляет(client, актор, товар, строка_заказа, данные):
    client.force_login(актор)
    response = client.post(
        reverse("admin:catalog_product_changelist"),
        {"action": "delete_selected", "_selected_action": [str(товар.pk)], **данные},
    )
    assert response.status_code == 302
    _всё_на_месте(товар, строка_заказа)


def test_вернуть_на_проверку_работает_и_сохраняет_связи(
    client, суперпользователь, товар, строка_заказа
):
    client.force_login(суперпользователь)
    response = client.post(
        reverse("admin:catalog_product_changelist"),
        {"action": "action_needs_review", "_selected_action": [str(товар.pk)], "index": "0"},
    )
    assert response.status_code == 302
    товар.refresh_from_db()
    assert товар.status == ProductStatus.NEEDS_REVIEW
    _всё_на_месте(товар, строка_заказа)
