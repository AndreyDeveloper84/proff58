"""Менеджерский переход заказа: матрица, резерв, событие.

Денежный контур, поэтому проверяем не только «статус сменился», а все три
побочных эффекта, из-за которых сервис и появился.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.core.exceptions import ValidationError

from apps.orders.fulfillment import advance_fulfillment, next_steps
from apps.orders.models import FulfillmentStatus, Order, ReservationStatus


@pytest.fixture
def заказ(db):
    return Order.objects.create(
        order_number="F-1",
        fulfillment_status=FulfillmentStatus.NEW,
        total=Decimal("1000.00"),
        reservation_status=ReservationStatus.HELD,
    )


def test_допустимый_переход_меняет_статус(заказ):
    advance_fulfillment(заказ.pk, FulfillmentStatus.CONFIRMED)

    заказ.refresh_from_db()
    assert заказ.fulfillment_status == FulfillmentStatus.CONFIRMED


def test_недопустимый_переход_отклоняется_с_подсказкой(заказ):
    Order.objects.filter(pk=заказ.pk).update(fulfillment_status=FulfillmentStatus.COMPLETED)

    with pytest.raises(ValidationError) as exc:
        advance_fulfillment(заказ.pk, FulfillmentStatus.NEW)

    text = " ".join(exc.value.messages)
    assert "нельзя перевести" in text
    assert "конечный статус" in text


def test_повтор_того_же_статуса_ничего_не_делает(заказ, django_capture_on_commit_callbacks):
    with mock.patch("apps.core.events.order_status_changed.send") as send:
        with django_capture_on_commit_callbacks(execute=True):
            advance_fulfillment(заказ.pk, FulfillmentStatus.NEW)

    assert send.call_count == 0


def test_событие_издаётся_после_коммита(заказ, django_capture_on_commit_callbacks):
    """На order_status_changed подписаны CRM и MAX-бот — покупатель узнаёт о смене."""
    with mock.patch("apps.core.events.order_status_changed.send") as send:
        with django_capture_on_commit_callbacks(execute=True):
            advance_fulfillment(заказ.pk, FulfillmentStatus.CONFIRMED)

    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["order_id"] == заказ.pk
    assert kwargs["old_status"] == FulfillmentStatus.NEW
    assert kwargs["new_status"] == FulfillmentStatus.CONFIRMED


def test_отмена_возвращает_резерв(заказ):
    """«Отменённый заказ с удержанным резервом» существовать не должен."""
    with mock.patch("apps.orders.reservation.release_reservation") as release:
        advance_fulfillment(заказ.pk, FulfillmentStatus.CANCELLED)

    release.assert_called_once_with(заказ.pk)


def test_переход_вперёд_резерв_не_трогает(заказ):
    with mock.patch("apps.orders.reservation.release_reservation") as release:
        advance_fulfillment(заказ.pk, FulfillmentStatus.CONFIRMED)

    assert release.call_count == 0


def test_неизвестный_статус_отклоняется(заказ):
    with pytest.raises(ValidationError):
        advance_fulfillment(заказ.pk, "пришелец")


@pytest.mark.parametrize(
    "статус,ожидаемые",
    [
        (FulfillmentStatus.NEW, ["confirmed", "cancelled"]),
        (FulfillmentStatus.CONFIRMED, ["assembling", "ready", "cancelled"]),
        (FulfillmentStatus.READY, ["shipped", "completed", "cancelled"]),
        (FulfillmentStatus.COMPLETED, []),
        (FulfillmentStatus.CANCELLED, []),
    ],
)
def test_шаги_идут_по_цепочке_отмена_последней(заказ, статус, ожидаемые):
    заказ.fulfillment_status = статус

    assert [value for value, _ in next_steps(заказ)] == ожидаемые


def test_шаги_подписаны_по_русски(заказ):
    assert next_steps(заказ) == [("confirmed", "Подтверждён"), ("cancelled", "Отменён")]
