"""Тесты API для 1С (/api/1c/...)."""

import json
from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus
from apps.pricing.models import PriceRecord
from apps.sync_1c import use_cases
from apps.sync_1c.api.parsers import OneCJSONParser
from apps.sync_1c.models import SyncLog

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
def test_products_import_creates(auth_client, django_capture_on_commit_callbacks):
    """Импорт асинхронный: 202 + batch_uid; задача ставится в on_commit (#272)."""
    payload = {
        "items": [
            {"external_id": "1c-100", "sku": "A-1", "name": "Дрель", "price": "1000", "stock": "3"}
        ]
    }
    with django_capture_on_commit_callbacks(execute=True):
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


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_import_task_deferred_to_on_commit(auth_client, django_capture_on_commit_callbacks):
    """Задача ставится в очередь только в transaction.on_commit (#272).

    Иначе при ATOMIC_REQUESTS=True воркер onec делает SyncLog.objects.get(id) до
    коммита прогона → DoesNotExist, импорт теряется (1С уже получила 202).
    """
    payload = {"items": [{"external_id": "1c-oc", "name": "X", "price": "1"}]}
    with mock.patch("apps.sync_1c.api.views.tasks.import_products_task.delay") as delay:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            resp = auth_client.post("/api/1c/products/import", payload, format="json")
            assert resp.status_code == 202
        # до коммита задача не поставлена, постановка отложена ровно одним колбэком
        assert delay.call_count == 0
        assert len(callbacks) == 1
        # эмулируем коммит → задача ставится с id уже существующего прогона
        callbacks[0]()
        assert delay.call_count == 1
        sync_log_id = delay.call_args.args[0]
        assert SyncLog.objects.filter(id=sync_log_id).exists()


def test_onec_parser_decodes_both_encodings():
    """Декодер 1С понимает и UTF-8, и Windows-1251 (1С 7.7 шлёт cp1251)."""
    assert OneCJSONParser.decode("Дрель".encode("cp1251")) == "Дрель"
    assert OneCJSONParser.decode("Дрель".encode()) == "Дрель"


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_import_accepts_cp1251_body(auth_client, django_capture_on_commit_callbacks):
    """1С 7.7 выгружает тело в Windows-1251 — кириллица не должна биться в кракозябры."""
    name = "Дрель ударная ЗУБР ЗДУ-810"
    body = json.dumps(
        {"items": [{"external_id": "1c-cp1251", "name": name, "price": "1000"}]},
        ensure_ascii=False,
    ).encode("cp1251")

    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post(
            "/api/1c/products/import",
            data=body,
            content_type="application/json; charset=windows-1251",
        )
    assert resp.status_code == 202

    p = Product.objects.get(code_1c="1c-cp1251")
    assert p.original_name == name  # корректная кириллица, а не «Äðåëü»


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_import_cp1251_without_charset_header(
    auth_client, django_capture_on_commit_callbacks
):
    """1С может не проставить charset — кодировку определяем по содержимому."""
    name = "Шуруповёрт аккумуляторный"
    body = json.dumps(
        {"items": [{"external_id": "1c-cp-noh", "name": name, "price": "1"}]},
        ensure_ascii=False,
    ).encode("cp1251")

    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post(
            "/api/1c/products/import", data=body, content_type="application/json"
        )
    assert resp.status_code == 202
    assert Product.objects.get(code_1c="1c-cp-noh").original_name == name


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_response_encoded_in_cp1251(auth_client):
    """Ответы 1С-эндпоинтов отдаются в Windows-1251 (1С читает их как cp1251)."""
    # detail с кириллицей: невалидный limit у snapshot отдаёт текст ошибки.
    resp = auth_client.get("/api/1c/snapshot/?limit=0")
    assert resp.status_code == 400
    assert "charset=windows-1251" in resp["Content-Type"].lower()
    # тело реально в cp1251, а не в utf-8
    assert "должен быть положительным".encode("cp1251") in resp.content
    assert "должен быть положительным".encode() not in resp.content
    assert "должен быть положительным" in resp.content.decode("cp1251")


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_update_does_not_create(auth_client, django_capture_on_commit_callbacks):
    """products/update не создаёт новый товар — отсутствующий уходит в skipped."""
    payload = {"items": [{"external_id": "1c-upd", "name": "Новый", "price": "500"}]}
    with django_capture_on_commit_callbacks(execute=True):
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
def test_stocks_update_requires_stock_field_400(auth_client):
    """Только идентификатор без stock/reserved/available_stock → 400 (контракт)."""
    resp = auth_client.post(
        "/api/1c/stocks/update",
        {"items": [{"external_id": "1c-300"}]},
        format="json",
    )
    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_stocks_update_zero_stock_is_valid(auth_client):
    """stock=0 (нулевой остаток) — валиден, не путать с отсутствием поля."""
    Product.objects.create(name="Т", code_1c="1c-301", slug="t-301")
    resp = auth_client.post(
        "/api/1c/stocks/update",
        {"items": [{"external_id": "1c-301", "stock": "0"}]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_endpoints_implemented(auth_client):
    """orders/new и orders/confirm реализованы (#50): не 501.

    Подробное покрытие — в test_orders_api.py."""
    assert auth_client.get("/api/1c/orders/new").status_code == 200
    # пустой батч → 400 (валидация конверта), а не 501
    assert (
        auth_client.post("/api/1c/orders/confirm", {"items": []}, format="json").status_code == 400
    )


@override_settings(ONEC_API_KEY="")
@pytest.mark.django_db
def test_empty_server_key_denies(auth_client):
    # если ключ на сервере не задан — доступ закрыт
    resp = auth_client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_enqueue_failure_marks_error(auth_client, django_capture_on_commit_callbacks):
    """Сбой брокера при постановке (в on_commit) → прогон ERROR (#272).

    Ответ уходит до коммита (202 accepted), поэтому синхронный 503 на сбой
    брокера уже не вернуть — сбой фиксируется в самом прогоне и виден 1С через
    опрос sync/<batch_uid>.
    """
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
        with django_capture_on_commit_callbacks(execute=True):
            resp = auth_client.post("/api/1c/products/import", payload, format="json")

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"

    sl = SyncLog.objects.get(batch_uid=body["batch_uid"])
    assert sl.result == SyncLog.SyncResult.ERROR
    assert sl.finished_at is not None
    assert sl.rows_total == 2 and sl.rows_error == 2
    assert sl.counters["errors"] == 2

    # 1С узнаёт о сбое через опрос статуса
    st = auth_client.get(f"/api/1c/sync/{body['batch_uid']}").json()
    assert st["status"] == "error"
    assert st["finished"] is True


@override_settings(ONEC_API_KEY=API_KEY, ONEC_MAX_ITEMS=2)
@pytest.mark.django_db
def test_items_over_limit_rejected_400(auth_client):
    payload = {"items": [{"external_id": f"m-{i}", "price": "1"} for i in range(3)]}
    resp = auth_client.post("/api/1c/prices/update", payload, format="json")
    assert resp.status_code == 400


# --- Снимок позиций (GET /api/1c/snapshot/) ---


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_returns_fields(auth_client):
    Product.objects.create(
        name="Дрель",
        code_1c="1c-snap-1",
        slug="snap-1",
        price="5900.00",
        currency="RUB",
        stock_quantity="7.000",
        reserved_quantity="2.000",
        available_quantity="5.000",
    )
    resp = auth_client.get("/api/1c/snapshot/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    row = body["results"][0]
    assert set(row) == {"code_1c", "price", "currency", "stock", "reserved", "available"}
    assert row["code_1c"] == "1c-snap-1"
    assert row["price"] == "5900.00"
    assert row["currency"] == "RUB"
    assert row["stock"] == "7.000"
    assert row["reserved"] == "2.000"
    assert row["available"] == "5.000"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_excludes_products_without_code_1c(auth_client):
    Product.objects.create(name="С кодом", code_1c="1c-snap-2", slug="snap-2")
    Product.objects.create(name="Без кода", code_1c=None, slug="snap-no-code")
    Product.objects.create(name="Пустой код", code_1c="", slug="snap-empty-code")
    resp = auth_client.get("/api/1c/snapshot/")
    body = resp.json()
    assert body["count"] == 1
    assert [r["code_1c"] for r in body["results"]] == ["1c-snap-2"]


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_includes_hidden_products(auth_client):
    """Скрытые на витрине позиции с code_1c всё равно попадают в снимок."""
    Product.objects.create(
        name="Черновик", code_1c="1c-hidden", slug="snap-hidden", status=ProductStatus.DRAFT
    )
    resp = auth_client.get("/api/1c/snapshot/")
    body = resp.json()
    assert [r["code_1c"] for r in body["results"]] == ["1c-hidden"]


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_pagination_and_next_offset(auth_client):
    for i in range(5):
        Product.objects.create(name=f"Т{i}", code_1c=f"1c-p-{i}", slug=f"snap-p-{i}")

    page1 = auth_client.get("/api/1c/snapshot/?limit=2&offset=0").json()
    assert page1["count"] == 5
    assert page1["limit"] == 2
    assert page1["offset"] == 0
    assert page1["next_offset"] == 2
    assert len(page1["results"]) == 2

    last = auth_client.get("/api/1c/snapshot/?limit=2&offset=4").json()
    assert last["next_offset"] is None
    assert len(last["results"]) == 1


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_stable_sort_by_code_then_id(auth_client):
    # одинаковый code_1c недопустим (unique), но порядок должен идти по code_1c, затем id
    Product.objects.create(name="B", code_1c="1c-b", slug="snap-sort-b")
    Product.objects.create(name="A", code_1c="1c-a", slug="snap-sort-a")
    Product.objects.create(name="C", code_1c="1c-c", slug="snap-sort-c")
    body = auth_client.get("/api/1c/snapshot/").json()
    assert [r["code_1c"] for r in body["results"]] == ["1c-a", "1c-b", "1c-c"]


@override_settings(ONEC_API_KEY=API_KEY, ONEC_MAX_ITEMS=3)
@pytest.mark.django_db
def test_snapshot_limit_clamped_to_max(auth_client):
    for i in range(5):
        Product.objects.create(name=f"Т{i}", code_1c=f"1c-clamp-{i}", slug=f"snap-clamp-{i}")
    body = auth_client.get("/api/1c/snapshot/?limit=100").json()
    assert body["limit"] == 3
    assert len(body["results"]) == 3
    assert body["next_offset"] == 3


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "limit=abc", "offset=-1", "offset=abc"])
def test_snapshot_invalid_params_400(auth_client, query):
    resp = auth_client.get(f"/api/1c/snapshot/?{query}")
    assert resp.status_code == 400
    assert "detail" in resp.json()


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_requires_key(client):
    resp = client.get("/api/1c/snapshot/")
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_price_null_with_currency(auth_client):
    Product.objects.create(name="Без цены", code_1c="1c-noprice", slug="snap-noprice", price=None)
    body = auth_client.get("/api/1c/snapshot/").json()
    row = body["results"][0]
    assert row["price"] is None
    assert row["currency"] == "RUB"
    # числа отдаются строками
    assert isinstance(row["stock"], str)


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_snapshot_currency_fallback_to_rub(auth_client):
    """Пустая валюта в БД → в снимке отдаётся дефолт RUB."""
    Product.objects.create(name="Пустая валюта", code_1c="1c-cur", slug="snap-cur", currency="")
    body = auth_client.get("/api/1c/snapshot/").json()
    assert body["results"][0]["currency"] == "RUB"


# --- external_batch_id (#58) ---


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_import_stores_external_batch_id(auth_client, django_capture_on_commit_callbacks):
    """external_batch_id из тела запроса сохраняется в SyncLog."""
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post(
            "/api/1c/products/import",
            {
                "items": [{"external_id": "eb-1", "name": "Товар", "price": "100"}],
                "external_batch_id": "BATCH-XYZ-001",
            },
            format="json",
        )
    assert resp.status_code == 202
    batch_uid = resp.json()["batch_uid"]
    sl = SyncLog.objects.get(batch_uid=batch_uid)
    assert sl.external_batch_id == "BATCH-XYZ-001"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_sync_status_returns_external_batch_id(auth_client):
    """GET /api/1c/sync/<uid>/ возвращает external_batch_id."""
    sync_log = use_cases.new_import_job(source_file="test", external_batch_id="EXT-42")
    st = auth_client.get(f"/api/1c/sync/{sync_log.batch_uid}").json()
    assert st["external_batch_id"] == "EXT-42"


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_products_import_without_external_batch_id(auth_client, django_capture_on_commit_callbacks):
    """Если external_batch_id не передан — поле пустое, не ошибка."""
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth_client.post(
            "/api/1c/products/import",
            {"items": [{"external_id": "eb-2", "name": "Товар2", "price": "200"}]},
            format="json",
        )
    assert resp.status_code == 202
    batch_uid = resp.json()["batch_uid"]
    sl = SyncLog.objects.get(batch_uid=batch_uid)
    assert sl.external_batch_id == ""
