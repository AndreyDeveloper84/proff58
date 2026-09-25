"""Правка состава заказа из админки через сервис (T8): пересчёт итога и резерва,
отказ при нехватке остатка, откат, повторное сохранение, заморозка оплаченного."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.orders.admin import OrderAdmin
from apps.orders.editing import update_quantities
from apps.orders.models import FulfillmentStatus, Order, PaymentStatus, ReservationStatus
from apps.orders.services import add_to_cart, place_order

User = get_user_model()
ГОСТЬ = {"customer_name": "Гость", "customer_phone": "+79001234567"}


@pytest.fixture
def менеджер(db):
    return User.objects.create_superuser(phone="+79993330001", password="pwd12345")


@pytest.fixture
def заказ(cart, product, product2):
    add_to_cart(cart, product, 2)  # 1000 × 2, остаток 10 → 8
    add_to_cart(cart, product2, 1)  # 500 × 1, остаток 5 → 4
    return place_order(cart, customer_data=ГОСТЬ)


def _stock(p):
    p.refresh_from_db()
    return p.available_quantity, p.reserved_quantity


def test_обычное_изменение_пересчитывает_итог_и_резерв(заказ, product, product2):
    item = заказ.items.get(product=product)
    order, log = update_quantities(заказ.pk, {item.pk: 3}, actor_id=1)
    item.refresh_from_db()
    assert item.quantity == 3 and item.line_total == Decimal("3000.00")
    assert order.total == Decimal("3500.00")
    assert _stock(product) == (Decimal("7"), Decimal("3"))
    assert _stock(product2) == (Decimal("4"), Decimal("1"))
    assert log and "2 → 3" in log[0]


def test_уменьшение_возвращает_остаток(заказ, product):
    item = заказ.items.get(product=product)
    update_quantities(заказ.pk, {item.pk: 1})
    assert _stock(product) == (Decimal("9"), Decimal("1"))
    assert Order.objects.get(pk=заказ.pk).total == Decimal("1500.00")


def test_удаление_строки(заказ, product2):
    item = заказ.items.get(product=product2)
    order, _ = update_quantities(заказ.pk, {item.pk: 0})
    assert not order.items.filter(pk=item.pk).exists()
    assert order.total == Decimal("2000.00")
    assert _stock(product2) == (Decimal("5"), Decimal("0"))


def test_нельзя_убрать_все_строки(заказ):
    with pytest.raises(ValidationError, match="отмените заказ"):
        update_quantities(заказ.pk, {it.pk: 0 for it in заказ.items.all()})


def test_недостаток_остатка_откатывает_всё(заказ, product, product2):
    i1 = заказ.items.get(product=product)
    i2 = заказ.items.get(product=product2)
    with pytest.raises(ValidationError, match="нет в наличии"):
        update_quantities(заказ.pk, {i1.pk: 3, i2.pk: 50})
    i1.refresh_from_db()
    assert i1.quantity == 2
    assert _stock(product) == (Decimal("8"), Decimal("2"))
    assert Order.objects.get(pk=заказ.pk).total == Decimal("2500.00")


def test_отрицательное_количество_отклоняется(заказ, product):
    item = заказ.items.get(product=product)
    with pytest.raises(ValidationError, match="отрицательным"):
        update_quantities(заказ.pk, {item.pk: -1})


def test_повторное_сохранение_ничего_не_меняет(заказ, product):
    item = заказ.items.get(product=product)
    update_quantities(заказ.pk, {item.pk: 3})
    order, log = update_quantities(заказ.pk, {item.pk: 3})
    assert log == []
    assert _stock(product) == (Decimal("7"), Decimal("3"))
    assert order.total == Decimal("3500.00")


def test_снятый_резерв_остаток_не_трогает(заказ, product):
    Order.objects.filter(pk=заказ.pk).update(reservation_status=ReservationStatus.RELEASED)
    item = заказ.items.get(product=product)
    update_quantities(заказ.pk, {item.pk: 5})
    assert _stock(product) == (Decimal("8"), Decimal("2"))  # как после place_order


@pytest.mark.parametrize(
    "поля",
    [
        {"payment_status": PaymentStatus.PAID},
        {"fulfillment_status": FulfillmentStatus.SHIPPED},
        {"reservation_status": ReservationStatus.CONFIRMED},
        {"promo_code": "SALE", "items_discount_total": Decimal("10.00")},
    ],
)
def test_оплаченный_или_отгруженный_не_правится(заказ, product, поля):
    Order.objects.filter(pk=заказ.pk).update(**поля)
    item = заказ.items.get(product=product)
    with pytest.raises(ValidationError, match="изменить нельзя"):
        update_quantities(заказ.pk, {item.pk: 1})


def test_у_оплаченного_финансовые_поля_только_чтение(заказ, менеджер, rf):
    Order.objects.filter(pk=заказ.pk).update(payment_status=PaymentStatus.PAID)
    заказ.refresh_from_db()
    admin_obj = OrderAdmin(Order, AdminSite())
    request = rf.get("/")
    request.user = менеджер
    ro = admin_obj.get_readonly_fields(request, заказ)
    assert {"total", "delivery_cost", "payment_status", "delivery_address"} <= set(ro)
    inline = admin_obj.inlines[0](Order, admin_obj.admin_site)
    assert "quantity" in inline.get_readonly_fields(request, заказ)
    assert inline.has_delete_permission(request, заказ) is False


def test_онлайн_оплата_статус_оплаты_не_правится_рукой(заказ, менеджер, rf):
    Order.objects.filter(pk=заказ.pk).update(payment_method="online")
    заказ.refresh_from_db()
    request = rf.get("/")
    request.user = менеджер
    assert "payment_status" in OrderAdmin(Order, AdminSite()).get_readonly_fields(request, заказ)


def _post_data(order, item_qty=None):
    item_qty = item_qty or {}
    items = list(order.items.order_by("pk"))
    data = {
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "customer_email": "",
        "customer_type": order.customer_type,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method or "",
        "sync_1c_status": order.sync_1c_status,
        "total": order.total,
        "delivery_method": order.delivery_method,
        "delivery_address": order.delivery_address,
        "delivery_zone": order.delivery_zone,
        "delivery_cost": "" if order.delivery_cost is None else order.delivery_cost,
        "delivery_calc_status": order.delivery_calc_status,
        "delivery_slot": "",
        "tracking_number": "",
        "comment": "",
        "company_name": "",
        "inn": "",
        "kpp": "",
        "legal_address": "",
        "user": "",
        "items-TOTAL_FORMS": len(items),
        "items-INITIAL_FORMS": len(items),
        "items-MIN_NUM_FORMS": 0,
        "items-MAX_NUM_FORMS": 1000,
    }
    for i, it in enumerate(items):
        data[f"items-{i}-id"] = it.pk
        data[f"items-{i}-order"] = order.pk
        data[f"items-{i}-quantity"] = item_qty.get(it.product_id, it.quantity)
    return data


def test_админка_сохраняет_через_сервис_и_пишет_журнал(client, менеджер, заказ, product):
    client.force_login(менеджер)
    url = reverse("admin:orders_order_change", args=[заказ.pk])
    resp = client.post(url, _post_data(заказ, {product.pk: 3}))
    assert resp.status_code == 302
    заказ.refresh_from_db()
    assert заказ.total == Decimal("3500.00")
    assert _stock(product) == (Decimal("7"), Decimal("3"))
    entries = [
        e
        for e in LogEntry.objects.filter(object_id=str(заказ.pk))
        if "2 → 3" in e.get_change_message()
    ]
    assert len(entries) == 1 and entries[0].user_id == менеджер.pk


def test_админка_при_нехватке_остатка_ничего_не_сохраняет(client, менеджер, заказ, product):
    client.force_login(менеджер)
    url = reverse("admin:orders_order_change", args=[заказ.pk])
    data = _post_data(заказ, {product.pk: 50})
    data["comment"] = "правка вместе с составом"
    resp = client.post(url, data, follow=True)
    assert "Изменения не сохранены" in resp.content.decode()
    заказ.refresh_from_db()
    assert заказ.comment == ""  # откатилось и сохранение самого заказа
    assert заказ.total == Decimal("2500.00")
    assert _stock(product) == (Decimal("8"), Decimal("2"))


def test_правка_итога_рукой_сверяется_с_формулой(client, менеджер, заказ):
    client.force_login(менеджер)
    url = reverse("admin:orders_order_change", args=[заказ.pk])
    data = _post_data(заказ)
    data["total"] = "1.00"
    resp = client.post(url, data)
    assert resp.status_code == 200
    assert "Сумма заказа должна быть" in resp.content.decode()
