"""Кнопки перевода статуса в админке заказа.

Ключевое свойство: состояние меняется ТОЛЬКО POST-ом. Ссылка-переход по GET
двигала бы заказ от случайного клика или префетча браузера, а на смену статуса
подписаны CRM и MAX-бот — покупатель получил бы уведомление о том, чего не было.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.orders.models import FulfillmentStatus, Order, ReservationStatus

User = get_user_model()


@pytest.fixture
def менеджер(db):
    return User.objects.create_superuser(phone="+79993330000", password="pwd12345")


@pytest.fixture
def заказ(db):
    return Order.objects.create(
        order_number="A-1",
        fulfillment_status=FulfillmentStatus.NEW,
        total=Decimal("5000.00"),
        customer_name="Иван Петров",
        customer_phone="+79001112233",
        reservation_status=ReservationStatus.HELD,
    )


def _url(заказ, target):
    return reverse("admin:orders_order_advance", args=[заказ.pk, target])


def test_get_показывает_подтверждение_и_не_меняет_статус(client, менеджер, заказ):
    client.force_login(менеджер)

    response = client.get(_url(заказ, FulfillmentStatus.CONFIRMED))

    заказ.refresh_from_db()
    assert response.status_code == 200
    assert заказ.fulfillment_status == FulfillmentStatus.NEW
    assert "Перевести заказ" in response.content.decode()


def test_post_переводит_статус(client, менеджер, заказ):
    client.force_login(менеджер)

    response = client.post(_url(заказ, FulfillmentStatus.CONFIRMED))

    заказ.refresh_from_db()
    assert response.status_code == 302
    assert заказ.fulfillment_status == FulfillmentStatus.CONFIRMED


def test_подтверждение_отмены_предупреждает_о_резерве(client, менеджер, заказ):
    client.force_login(менеджер)

    body = client.get(_url(заказ, FulfillmentStatus.CANCELLED)).content.decode()

    assert "Резерв товаров вернётся" in body
    assert "необратима" in body


def test_недопустимый_переход_не_проходит_и_объясняет(client, менеджер, заказ):
    Order.objects.filter(pk=заказ.pk).update(fulfillment_status=FulfillmentStatus.COMPLETED)
    client.force_login(менеджер)

    client.post(_url(заказ, FulfillmentStatus.NEW), follow=True)

    заказ.refresh_from_db()
    assert заказ.fulfillment_status == FulfillmentStatus.COMPLETED


def test_переход_пишется_в_историю(client, менеджер, заказ):
    """«Кто поставил этот статус» раньше нельзя было узнать нигде."""
    client.force_login(менеджер)

    client.post(_url(заказ, FulfillmentStatus.CONFIRMED))

    entry = LogEntry.objects.filter(object_id=str(заказ.pk)).first()
    assert entry is not None
    assert "Подтверждён" in entry.get_change_message()
    assert entry.user_id == менеджер.pk


def test_чужому_без_прав_нельзя(client, db, заказ):
    user = User.objects.create_user(phone="+79994440000", password="pwd12345", is_staff=True)
    client.force_login(user)

    response = client.post(_url(заказ, FulfillmentStatus.CONFIRMED))

    заказ.refresh_from_db()
    assert response.status_code in (302, 403)
    assert заказ.fulfillment_status == FulfillmentStatus.NEW


def test_обработка_только_для_чтения_в_форме():
    """Статус двигается кнопками; поле оставлено справочным, чтобы его не правили."""
    from django.contrib.admin.sites import AdminSite

    from apps.orders.admin import OrderAdmin

    assert "fulfillment_status" in OrderAdmin(Order, AdminSite()).readonly_fields


def test_список_показывает_один_статус_и_кнопки():
    from django.contrib.admin.sites import AdminSite

    from apps.orders.admin import OrderAdmin

    display = OrderAdmin(Order, AdminSite()).list_display
    assert "status_badge" in display and "next_action" in display
    # четырёх технических статусов в списке больше нет
    assert "fulfillment_status" not in display
    assert "sync_1c_status" not in display
