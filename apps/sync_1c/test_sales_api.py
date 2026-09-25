"""Приём продаж из 1С: /api/1c/sales/upload.

Продажи магазина — основной источник «Хитов продаж»: сайт видит только свои
заказы, а розница идёт мимо него. Проверяем контракт, идемпотентность и то, что
неизвестная 1С-номенклатура не ломает выгрузку.
"""

from datetime import date

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductSalesFact, ProductStatus, SalesSource
from apps.catalog.sales import rebuild_sales_stats
from apps.sync_1c.models import SyncLog

API_KEY = "test-key-sales"
URL = "/api/1c/sales/upload"


@pytest.fixture
def auth_client():
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=API_KEY)
    return client


@pytest.fixture
def product(db):
    return Product.objects.create(
        code_1c="1c-sale-1",
        article="ART-SALE-1",
        name="Перфоратор",
        slug="perforator-sale-1",
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_без_ключа_доступа_нет():
    resp = APIClient().post(
        URL, {"items": [{"code_1c": "x", "date": "2026-07-01", "quantity": 1}]}, format="json"
    )
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_принимает_продажи_и_считает_их(auth_client, product):
    payload = {
        "items": [
            {"code_1c": "1c-sale-1", "date": "2026-07-01", "quantity": "3"},
            {"code_1c": "1c-sale-1", "date": "2026-07-02", "quantity": "2"},
        ]
    }

    resp = auth_client.post(URL, payload, format="json")

    assert resp.status_code == 200
    assert ProductSalesFact.objects.filter(source=SalesSource.ONEC).count() == 2
    assert SyncLog.objects.filter(sync_type=SyncLog.SyncType.SALES).exists()


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_повторная_выгрузка_не_удваивает(auth_client, product):
    payload = {"items": [{"code_1c": "1c-sale-1", "date": "2026-07-01", "quantity": "3"}]}

    auth_client.post(URL, payload, format="json")
    auth_client.post(URL, payload, format="json")

    fact = ProductSalesFact.objects.get()
    assert fact.quantity == 3


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_несколько_документов_за_день_складываются(auth_client, product):
    payload = {
        "items": [
            {"code_1c": "1c-sale-1", "date": "2026-07-01", "quantity": "2"},
            {"code_1c": "1c-sale-1", "date": "2026-07-01", "quantity": "5"},
        ]
    }

    auth_client.post(URL, payload, format="json")

    assert ProductSalesFact.objects.get().quantity == 7


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_неизвестная_номенклатура_идёт_в_skipped(auth_client, product):
    payload = {
        "items": [
            {"code_1c": "1c-sale-1", "date": "2026-07-01", "quantity": "1"},
            {"code_1c": "нет-такого", "date": "2026-07-01", "quantity": "9"},
        ]
    }

    resp = auth_client.post(URL, payload, format="json")

    body = resp.json()
    assert body["skipped"] == 1
    assert ProductSalesFact.objects.count() == 1


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_матчинг_по_артикулу_когда_нет_кода(auth_client, product):
    payload = {"items": [{"sku": "ART-SALE-1", "date": "2026-07-01", "quantity": "4"}]}

    auth_client.post(URL, payload, format="json")

    assert ProductSalesFact.objects.get().product_id == product.id


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_строка_без_идентификатора_отвергается(auth_client):
    resp = auth_client.post(
        URL, {"items": [{"date": "2026-07-01", "quantity": "1"}]}, format="json"
    )

    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_пустой_конверт_отвергается(auth_client):
    assert auth_client.post(URL, {"items": []}, format="json").status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_ответ_в_cp1251(auth_client):
    """1С 7.7 читает только cp1251 — иначе кириллица в ответе «ломается»."""
    resp = auth_client.post(URL, {"items": []}, format="json")

    assert "windows-1251" in resp["Content-Type"].lower()


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_выгрузка_1с_доходит_до_витрины(auth_client, product, settings):
    """Сквозной путь: выгрузка → факты → рейтинг → бейдж «Хит»."""
    settings.SALES_HIT_MIN_QUANTITY = 1
    auth_client.post(
        URL,
        {"items": [{"code_1c": "1c-sale-1", "date": "2026-07-01", "quantity": "12"}]},
        format="json",
    )
    rebuild_sales_stats(today=date(2026, 7, 2))

    product.refresh_from_db()
    assert product.sales_stat.is_hit is True
    assert product.sales_stat.rank == 1
