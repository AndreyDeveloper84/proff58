"""Тесты API для 1С (/api/1c/...)."""

from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus
from apps.sync_1c import use_cases
from apps.sync_1c.models import PriceRecord, SyncLog

API_KEY = "test-key-123"
EAGER = {"CELERY_TASK_ALWAYS_EAGER": True, "CELERY_TASK_EAGER_PROPAGATES": True}


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def auth_client():
    c = APIClient()
    c.credentials(HTTP_X_API_KEY=API_KEY)
    return c


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_products_import_requires_key(client):
    resp = client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_import_creates(auth_client):
    """Импорт асинхронный: 202 + batch_uid; в EAGER задача отрабатывает сразу."""
    payload = {
        "items": [
            {"external_id": "1c-100", "sku": "A-1", "name": "Дрель", "price": "1000", "stock": "3"}
        ]
    }
    resp = auth_client.post("/api/1c/products/import", payload, format="json")
    assert resp.status_code == 202
    batch_uid = resp.json()["batch_uid"]

    p = Product.objects.get(code_1c="1c-100")
    assert p.price == 1000
    assert p.status == ProductStatus.NEEDS_REVIEW

    st = auth_client.get(f"/api/1c/sync/{batch_uid}").json()
    assert st["status"] == "ok"
    assert st["finished"] is True
    assert st["created"] == 1


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_update_does_not_create(auth_client):
    """products/update не создаёт новый товар — отсутствующий уходит в skipped."""
    payload = {"items": [{"external_id": "1c-upd", "name": "Новый", "price": "500"}]}
    resp = auth_client.post("/api/1c/products/update", payload, format="json")
    assert resp.status_code == 202
    batch_uid = resp.json()["batch_uid"]
    assert Product.objects.filter(code_1c="1c-upd").count() == 0

    st = auth_client.get(f"/api/1c/sync/{batch_uid}").json()
    assert st["created"] == 0
    assert st["skipped"] == 1


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_sync_status_running_before_task_finishes(auth_client):
    """Прогон создан, но задача ещё не отработала → running + нулевые counters."""
    sync_log = use_cases.new_import_job(source_file="api:products/import")
    st = auth_client.get(f"/api/1c/sync/{sync_log.batch_uid}").json()
    assert st["status"] == "running"
    assert st["finished"] is False
    for key in ("created", "updated", "skipped", "uncategorized", "errors"):
        assert st[key] == 0


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_sync_status_unknown_batch(auth_client):
    resp = auth_client.get("/api/1c/sync/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_products_import_validation_error(auth_client):
    # элемент без единого идентификатора
    resp = auth_client.post(
        "/api/1c/products/import", {"items": [{"name": "Без id"}]}, format="json"
    )
    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_prices_update(auth_client):
    Product.objects.create(name="Т", code_1c="1c-200", slug="t-200")
    resp = auth_client.post(
        "/api/1c/prices/update",
        {"items": [{"external_id": "1c-200", "price": "777"}]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1
    assert Product.objects.get(code_1c="1c-200").price == 777


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_prices_update_accepts_price_type(auth_client):
    """API принимает price_type; разные типы цен живут как отдельные current-записи."""
    Product.objects.create(name="Т", code_1c="1c-201", slug="t-201")

    auth_client.post(
        "/api/1c/prices/update",
        {"items": [{"external_id": "1c-201", "price": "777", "price_type": "retail"}]},
        format="json",
    )
    resp = auth_client.post(
        "/api/1c/prices/update",
        {"items": [{"external_id": "1c-201", "price": "650", "price_type": "wholesale"}]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1

    # розничная актуальная цена не снята другим типом цены
    assert PriceRecord.objects.filter(
        code_1c="1c-201", price_type="retail", value=777, is_current=True
    ).exists()
    # появилась актуальная оптовая
    assert PriceRecord.objects.filter(
        code_1c="1c-201", price_type="wholesale", value=650, is_current=True
    ).exists()


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_stocks_update(auth_client):
    Product.objects.create(name="Т", code_1c="1c-300", slug="t-300")
    resp = auth_client.post(
        "/api/1c/stocks/update",
        {"items": [{"external_id": "1c-300", "stock": "10", "reserved": "2"}]},
        format="json",
    )
    assert resp.status_code == 200
    p = Product.objects.get(code_1c="1c-300")
    assert p.stock_quantity == 10
    assert p.available_quantity == 8


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_endpoints_are_stubbed(auth_client):
    assert auth_client.get("/api/1c/orders/new").status_code == 501
    assert auth_client.post("/api/1c/orders/confirm", {}, format="json").status_code == 501


@override_settings(ONEC_API_KEY="")
@pytest.mark.django_db
def test_empty_server_key_denies(auth_client):
    # если ключ на сервере не задан — доступ закрыт
    resp = auth_client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_enqueue_failure_returns_503_and_marks_error(auth_client):
    """Брокер недоступен → 503, безопасный detail, прогон ERROR (не RUNNING)."""
    payload = {
        "items": [
            {"external_id": "e-1", "name": "X", "price": "1"},
            {"external_id": "e-2", "name": "Y", "price": "2"},
        ]
    }
    with mock.patch(
        "apps.sync_1c.api.views.tasks.import_products_task.delay",
        side_effect=Exception("broker down"),
    ):
        resp = auth_client.post("/api/1c/products/import", payload, format="json")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    assert "broker" not in body["detail"]  # техдетали наружу не уходят

    sl = SyncLog.objects.get(batch_uid=body["batch_uid"])
    assert sl.result == SyncLog.SyncResult.ERROR
    assert sl.finished_at is not None
    assert sl.rows_total == 2 and sl.rows_error == 2
    assert sl.counters["errors"] == 2


@override_settings(ONEC_API_KEY=API_KEY, ONEC_MAX_ITEMS=2)
@pytest.mark.django_db
def test_items_over_limit_rejected_400(auth_client):
    payload = {"items": [{"external_id": f"m-{i}", "price": "1"} for i in range(3)]}
    resp = auth_client.post("/api/1c/prices/update", payload, format="json")
    assert resp.status_code == 400
