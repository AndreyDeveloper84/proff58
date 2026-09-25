"""Отмена заказа самим покупателем: правило, побочные эффекты и эндпоинт.

Решение владельца от 03.08.2026: покупатель отменяет сам, пока обработка в
«Новый» или «Подтверждён». Дальше товар уже снят с полок — только через
менеджера. Оплаченный заказ покупатель не отменяет: автовозврата денег нет.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import User
from apps.orders.fulfillment import can_customer_cancel, cancel_by_customer
from apps.orders.models import (
    FulfillmentStatus,
    Order,
    PaymentStatus,
    ReservationStatus,
    Sync1CStatus,
)


@pytest.fixture
def покупатель(db):
    return User.objects.create_user(email="buyer@proff58.ru", password="x", phone="+79990000001")


@pytest.fixture
def заказ(db, покупатель):
    return Order.objects.create(
        order_number="C-1",
        user=покупатель,
        fulfillment_status=FulfillmentStatus.NEW,
        payment_status=PaymentStatus.PENDING,
        total=Decimal("1000.00"),
        reservation_status=ReservationStatus.HELD,
    )


# --- Правило ---


@pytest.mark.parametrize(
    "статус,можно",
    [
        (FulfillmentStatus.NEW, True),
        (FulfillmentStatus.CONFIRMED, True),
        (FulfillmentStatus.ASSEMBLING, False),
        (FulfillmentStatus.READY, False),
        (FulfillmentStatus.SHIPPED, False),
        (FulfillmentStatus.COMPLETED, False),
        (FulfillmentStatus.CANCELLED, False),
    ],
)
def test_отмена_доступна_только_до_сборки(заказ, статус, можно):
    Order.objects.filter(pk=заказ.pk).update(fulfillment_status=статус)
    заказ.refresh_from_db()

    assert can_customer_cancel(заказ) is можно


def test_собираемый_заказ_отменить_нельзя(заказ):
    Order.objects.filter(pk=заказ.pk).update(fulfillment_status=FulfillmentStatus.ASSEMBLING)

    with pytest.raises(ValidationError) as exc:
        cancel_by_customer(заказ.pk)

    text = " ".join(exc.value.messages)
    assert "Собирается" in text
    assert "менеджер" in text
    заказ.refresh_from_db()
    assert заказ.fulfillment_status == FulfillmentStatus.ASSEMBLING


def test_оплаченный_заказ_отменяет_только_менеджер(заказ):
    Order.objects.filter(pk=заказ.pk).update(payment_status=PaymentStatus.PAID)
    заказ.refresh_from_db()

    assert can_customer_cancel(заказ) is False
    with pytest.raises(ValidationError) as exc:
        cancel_by_customer(заказ.pk)

    assert "оплачен" in " ".join(exc.value.messages)


# --- Побочные эффекты ---


def test_отмена_переводит_статус_и_возвращает_резерв(заказ):
    cancel_by_customer(заказ.pk, actor_id=заказ.user_id)

    заказ.refresh_from_db()
    assert заказ.fulfillment_status == FulfillmentStatus.CANCELLED
    # Резерв снимается в той же транзакции: «отменён, но остаток удержан» —
    # состояние, которого не должно существовать даже на миг.
    assert заказ.reservation_status == ReservationStatus.RELEASED


def test_отмена_издаёт_событие_после_коммита(заказ, django_capture_on_commit_callbacks):
    """На order_status_changed подписаны CRM и MAX-бот — иначе покупатель не узнает."""
    with mock.patch("apps.core.events.order_status_changed.send") as send:
        with django_capture_on_commit_callbacks(execute=True):
            cancel_by_customer(заказ.pk)

    assert send.call_count == 1
    assert send.call_args.kwargs["new_status"] == FulfillmentStatus.CANCELLED


def test_повторная_отмена_не_ошибка(заказ, django_capture_on_commit_callbacks):
    cancel_by_customer(заказ.pk)

    with mock.patch("apps.core.events.order_status_changed.send") as send:
        with django_capture_on_commit_callbacks(execute=True):
            cancel_by_customer(заказ.pk)

    assert send.call_count == 0  # второй раз — no-op, а не второе событие


def test_отменённый_заказ_не_уедет_в_1С(заказ):
    """1С забирает заказы через export_new_orders — отменённые она не видит."""
    from apps.sync_1c.use_cases import export_new_orders

    cancel_by_customer(заказ.pk)

    _, items = export_new_orders()
    assert all(item["order_number"] != "C-1" for item in items)


def test_отмена_после_выгрузки_попадает_в_лог(заказ, caplog):
    """Обратного канала «заказ отменён» в контракте 1С нет — менеджер снимает вручную."""
    Order.objects.filter(pk=заказ.pk).update(sync_1c_status=Sync1CStatus.EXPORTED)

    with caplog.at_level("WARNING"):
        cancel_by_customer(заказ.pk)

    assert any("ПОСЛЕ выгрузки в 1С" in r.getMessage() for r in caplog.records)


# --- Эндпоинт ---


def test_владелец_отменяет_через_api(client, покупатель, заказ):
    client.force_login(покупатель)

    response = client.post(reverse("orders_api:order-cancel", args=["C-1"]))

    assert response.status_code == 200
    assert response.json()["fulfillment_status"] == FulfillmentStatus.CANCELLED
    assert response.json()["can_cancel"] is False


def test_чужой_заказ_не_отменить(client, db, заказ):
    другой = User.objects.create_user(email="other@proff58.ru", password="x", phone="+79990000002")
    client.force_login(другой)

    response = client.post(reverse("orders_api:order-cancel", args=["C-1"]))

    assert response.status_code == 404
    заказ.refresh_from_db()
    assert заказ.fulfillment_status == FulfillmentStatus.NEW


def test_гостю_отмена_недоступна(client, заказ):
    response = client.post(reverse("orders_api:order-cancel", args=["C-1"]))

    assert response.status_code in (401, 403)


def test_недопустимая_отмена_отвечает_409_с_текстом(client, покупатель, заказ):
    """409, а не 400: запрос корректен, просто заказ ушёл вперёд — фронт покажет статус."""
    Order.objects.filter(pk=заказ.pk).update(fulfillment_status=FulfillmentStatus.SHIPPED)
    client.force_login(покупатель)

    response = client.post(reverse("orders_api:order-cancel", args=["C-1"]))

    assert response.status_code == 409
    assert "менеджер" in response.json()["detail"]


def test_флаг_can_cancel_виден_в_карточке_заказа(client, покупатель, заказ):
    client.force_login(покупатель)

    response = client.get(reverse("orders_api:order-detail", args=["C-1"]))

    assert response.status_code == 200
    assert response.json()["can_cancel"] is True
