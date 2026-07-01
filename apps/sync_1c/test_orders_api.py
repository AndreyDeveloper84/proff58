"""Тесты API заказов для 1С (#50): GET /orders/new и POST /orders/confirm.

Стиль — как в test_api.py: override_settings(ONEC_API_KEY=...), фикстура
auth_client с X-Api-Key, @pytest.mark.django_db.
"""

from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.events import order_status_changed
from apps.orders.models import (
    FulfillmentStatus,
    Order,
    OrderItem,
    PaymentStatus,
    Sync1CStatus,
)
from apps.sync_1c.models import SyncLog

API_KEY = "test-key-123"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def auth_client():
    c = APIClient()
    c.credentials(HTTP_X_API_KEY=API_KEY)
    return c


def make_order(**kwargs):
    """Создать заказ с одной строкой-снимком (минимальный валидный заказ)."""
    defaults = dict(
        order_number=kwargs.pop("order_number", "P-2026-000001"),
        customer_name="Иван Иванов",
        customer_phone="+79000000000",
        customer_email="client@example.com",
        payment_method="online",
        total=Decimal("5900.00"),
        currency="RUB",
    )
    defaults.update(kwargs)
    order = Order.objects.create(**defaults)
    OrderItem.objects.create(
        order=order,
        code_1c="1c-000123",
        article="BOSCH-GSB13RE",
        name="Дрель ударная BOSCH GSB 13 RE",
        unit="шт",
        price_final=Decimal("5900.00"),
        quantity=1,
        line_total=Decimal("5900.00"),
        currency="RUB",
    )
    return order


@pytest.fixture
def capture_status_events():
    """Собрать все order_status_changed, отправленные за время теста."""
    received = []

    def handler(sender, **kwargs):
        received.append(kwargs)

    order_status_changed.connect(handler)
    yield received
    order_status_changed.disconnect(handler)


# --- Авторизация ---


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_new_requires_key(client):
    assert client.get("/api/1c/orders/new").status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_confirm_requires_key(client):
    assert client.post("/api/1c/orders/confirm", {"items": []}, format="json").status_code == 403


# --- GET /orders/new ---


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_new_returns_pending_snapshot(auth_client):
    """Заказ отдаётся в форме §5.6 со СНИМКОМ цены/товара."""
    make_order()
    resp = auth_client.get("/api/1c/orders/new")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    order_data = items[0]
    assert order_data["order_number"] == "P-2026-000001"
    assert order_data["fulfillment_status"] == "new"
    assert order_data["payment"]["status"] == "pending"
    assert order_data["totals"]["total"] == "5900.00"
    assert order_data["delivery"]["cost"] == "0.00"
    line = order_data["items"][0]
    assert line["line_id"] == 1
    assert line["external_id"] == "1c-000123"
    assert line["sku"] == "BOSCH-GSB13RE"
    assert line["name"] == "Дрель ударная BOSCH GSB 13 RE"
    assert line["price"] == "5900.00"
    assert line["total"] == "5900.00"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_new_does_not_change_sync_status(auth_client):
    """После GET заказ остаётся pending (at-least-once, не exported)."""
    order = make_order()
    auth_client.get("/api/1c/orders/new")
    order.refresh_from_db()
    assert order.sync_1c_status == Sync1CStatus.PENDING


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_new_excludes_exported_cancelled_expired(auth_client):
    """exported / cancelled / payment=expired не попадают; pending B2B — попадает."""
    make_order(order_number="P-OK", customer_type="b2b", payment_status=PaymentStatus.PENDING)
    make_order(order_number="P-EXPORTED", sync_1c_status=Sync1CStatus.EXPORTED)
    make_order(order_number="P-CANCELLED", fulfillment_status=FulfillmentStatus.CANCELLED)
    make_order(order_number="P-EXPIRED", payment_status=PaymentStatus.EXPIRED)

    items = auth_client.get("/api/1c/orders/new").json()["items"]
    numbers = {i["order_number"] for i in items}
    assert numbers == {"P-OK"}


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_new_writes_sync_log(auth_client):
    make_order()
    auth_client.get("/api/1c/orders/new")
    log = SyncLog.objects.filter(sync_type=SyncLog.SyncType.ORDERS).latest("started_at")
    assert log.result == SyncLog.SyncResult.OK
    assert log.rows_total == 1
    assert log.rows_ok == 1


# --- POST /orders/confirm ---


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_success_with_reserve(
    auth_client, capture_status_events, django_capture_on_commit_callbacks
):
    """confirm+reserve: fulfillment=confirmed, ack сохранён, exported + exported_at,
    событие ровно один раз."""
    order = make_order()
    reserved_until = "2026-06-17T10:30:00+03:00"
    payload = {
        "items": [
            {
                "site_order_id": order.id,
                "order_number": order.order_number,
                "onec_order_id": "1c-order-987",
                "onec_order_number": "УТ-000987",
                "fulfillment_status": "confirmed",
                "reserve": {"ok": True, "reserved_until": reserved_until},
            }
        ]
    }
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["status"] == "ok"
    assert "batch_uid" in body

    order.refresh_from_db()
    assert order.fulfillment_status == FulfillmentStatus.CONFIRMED
    assert order.external_order_id == "1c-order-987"
    assert order.external_order_number == "УТ-000987"
    assert order.reserved_until is not None
    assert order.sync_1c_status == Sync1CStatus.EXPORTED
    assert order.exported_at is not None

    assert len(capture_status_events) == 1
    evt = capture_status_events[0]
    assert evt["order_id"] == order.id
    assert evt["old_status"] == "new"
    assert evt["new_status"] == "confirmed"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_invalid_transition_keeps_ack(
    auth_client, capture_status_events, django_capture_on_commit_callbacks
):
    """new→completed с onec_order_id: ack применён (sync=exported), fulfillment
    остаётся new, per-item error, HTTP 200, события нет."""
    order = make_order()
    payload = {
        "items": [
            {
                "site_order_id": order.id,
                "onec_order_id": "1c-order-987",
                "fulfillment_status": "completed",
            }
        ]
    }
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["status"] == "error"

    order.refresh_from_db()
    # sync-ack применён несмотря на ошибку перехода (оси независимы)
    assert order.sync_1c_status == Sync1CStatus.EXPORTED
    assert order.external_order_id == "1c-order-987"
    assert order.exported_at is not None
    # fulfillment не сдвинулся
    assert order.fulfillment_status == FulfillmentStatus.NEW
    assert capture_status_events == []


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_primary_without_onec_id_errors(auth_client):
    """Первичный confirm pending-заказа без onec_order_id → per-item error,
    заказ остаётся pending."""
    order = make_order()
    payload = {"items": [{"site_order_id": order.id, "fulfillment_status": "confirmed"}]}
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["status"] == "error"
    assert "onec_order_id" in item["detail"]

    order.refresh_from_db()
    assert order.sync_1c_status == Sync1CStatus.PENDING
    assert order.fulfillment_status == FulfillmentStatus.NEW
    assert order.external_order_id in (None, "")


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
@pytest.mark.parametrize("blank", ["", "   "])
def test_confirm_primary_with_blank_onec_id_errors(auth_client, blank):
    """Пустой/пробельный onec_order_id = «нет идентификатора» (#273).

    Иначе ack пропускается, заказ остаётся pending и выгружается снова и снова,
    либо в external_order_id записывается "" как «настоящий» документ 1С.
    """
    order = make_order()
    payload = {
        "items": [
            {"site_order_id": order.id, "onec_order_id": blank, "fulfillment_status": "confirmed"}
        ]
    }
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["status"] == "error"
    assert "onec_order_id" in item["detail"]

    order.refresh_from_db()
    assert order.sync_1c_status == Sync1CStatus.PENDING  # остаётся pending, не exported
    assert order.fulfillment_status == FulfillmentStatus.NEW
    assert order.external_order_id in (None, "")  # "" не записан как документ 1С


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_reserve_failed_keeps_fulfillment(auth_client):
    """reserve.ok=false (с onec_order_id): fulfillment остаётся new, sync=exported,
    причина — в SyncLog.error_details."""
    order = make_order()
    payload = {
        "items": [
            {
                "site_order_id": order.id,
                "onec_order_id": "1c-order-987",
                "fulfillment_status": "new",
                "reserve": {
                    "ok": False,
                    "lines": [
                        {"external_id": "1c-000123", "requested": "3.000", "available": "1.000"}
                    ],
                },
            }
        ]
    }
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200

    order.refresh_from_db()
    assert order.fulfillment_status == FulfillmentStatus.NEW
    assert order.sync_1c_status == Sync1CStatus.EXPORTED
    assert order.external_order_id == "1c-order-987"

    log = SyncLog.objects.filter(sync_type=SyncLog.SyncType.ORDERS).latest("started_at")
    assert "Резерв" in log.error_details


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_idempotent_same_status(
    auth_client, capture_status_events, django_capture_on_commit_callbacks
):
    """Повтор того же confirmed → no-op: без нового события, exported_at не изменился."""
    order = make_order(fulfillment_status=FulfillmentStatus.CONFIRMED)
    order.sync_1c_status = Sync1CStatus.EXPORTED
    order.exported_at = timezone.now()
    order.save()
    first_exported_at = order.exported_at

    payload = {
        "items": [
            {
                "site_order_id": order.id,
                "onec_order_id": "1c-order-987",
                "fulfillment_status": "confirmed",
            }
        ]
    }
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["status"] == "ok"

    order.refresh_from_db()
    assert order.fulfillment_status == FulfillmentStatus.CONFIRMED
    assert order.exported_at == first_exported_at
    assert capture_status_events == []


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_shipped_with_tracking(auth_client):
    """ready→shipped с tracking → tracking_number сохранён."""
    order = make_order(fulfillment_status=FulfillmentStatus.READY)
    order.sync_1c_status = Sync1CStatus.EXPORTED
    order.exported_at = timezone.now()
    order.save()

    payload = {
        "items": [
            {
                "site_order_id": order.id,
                "onec_order_id": "1c-order-987",
                "fulfillment_status": "shipped",
                "tracking": "PEK-123456",
            }
        ]
    }
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["status"] == "ok"

    order.refresh_from_db()
    assert order.fulfillment_status == FulfillmentStatus.SHIPPED
    assert order.tracking_number == "PEK-123456"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_unknown_order_per_item_error(auth_client):
    """Неизвестный заказ → per-item error (не 500)."""
    payload = {"items": [{"site_order_id": 999999, "onec_order_id": "1c-x"}]}
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["status"] == "error"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_no_identifier_400(auth_client):
    """Нет идентификатора заказа → 400 (ошибка валидации конверта)."""
    payload = {"items": [{"onec_order_id": "1c-x"}]}
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_empty_items_400(auth_client):
    resp = auth_client.post("/api/1c/orders/confirm", {"items": []}, format="json")
    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_confirm_writes_sync_log_with_errors(auth_client):
    """SyncLog(orders) создаётся; ошибки видны в error_details (partial)."""
    order = make_order()
    payload = {
        "items": [
            {"site_order_id": order.id, "onec_order_id": "1c-o", "fulfillment_status": "confirmed"},
            {"site_order_id": 999999, "onec_order_id": "1c-x"},
        ]
    }
    resp = auth_client.post("/api/1c/orders/confirm", payload, format="json")
    assert resp.status_code == 200

    log = SyncLog.objects.filter(sync_type=SyncLog.SyncType.ORDERS).latest("started_at")
    assert log.rows_total == 2
    assert log.rows_ok == 1
    assert log.rows_error == 1
    assert log.result == SyncLog.SyncResult.PARTIAL
    assert log.error_details
