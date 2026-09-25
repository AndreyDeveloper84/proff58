"""Тесты команды apply_stocks_1c: ремонт выгрузки, заливка остатков, публикация."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog.models import Category, Product, ProductStatus, StockStatus
from apps.sync_1c import use_cases
from apps.sync_1c.management.commands.apply_stocks_1c import parse_stock_items
from apps.sync_1c.models import SyncLog

# Сырая выгрузка 1С с реальными дефектами: группа с children; у листьев пропущена
# запятая после "name" перед "barcode"; висячие запятые перед } и ]; таб в имени.
RAW_1C = (
    "[\n"
    "{\n"
    '"ProductGroup": "1",\n'
    '"external_id": "g1",\n'
    '"name": "Электроинструмент",\n'
    '"children": [\n'
    "{\n"
    '"ProductGroup": "0",\n'
    '"external_id": "P-IN",\n'
    '"name": "Дрель\tударная"\n'
    '"barcode": "",\n'
    '"stock": "5",\n'
    '"is_active": "1",\n'
    "},\n"
    "{\n"
    '"ProductGroup": "0",\n'
    '"external_id": "P-ZERO",\n'
    '"name": "Шуруповёрт"\n'
    '"barcode": "",\n'
    '"stock": "0",\n'
    '"is_active": "1",\n'
    "},\n"
    "{\n"
    '"ProductGroup": "0",\n'
    '"external_id": "P-HID",\n'
    '"name": "Перфоратор"\n'
    '"barcode": "",\n'
    '"stock": "3",\n'
    '"is_active": "1",\n'
    "},\n"
    "]\n"
    "}\n"
    "]\n"
)


def test_parse_stock_items_repairs_defects():
    items = parse_stock_items(RAW_1C)
    assert items == [
        {"code_1c": "P-IN", "stock": "5"},
        {"code_1c": "P-ZERO", "stock": "0"},
        {"code_1c": "P-HID", "stock": "3"},
    ]


def _write(tmp_path):
    f = tmp_path / "Catalog_stocks.json"
    f.write_text(RAW_1C, encoding="cp1251")
    return str(f)


def _catalog():
    visible = Category.add_root(name="Витрина", slug="vit", on_site=True, is_active=True)
    hidden = Category.add_root(name="Скрытая", slug="hid", on_site=False, is_active=True)
    p_in = Product.objects.create(
        name="Дрель", slug="p-in", code_1c="P-IN", category=visible, status=ProductStatus.IMPORTED
    )
    p_zero = Product.objects.create(
        name="Шурик",
        slug="p-zero",
        code_1c="P-ZERO",
        category=visible,
        status=ProductStatus.IMPORTED,
    )
    p_hid = Product.objects.create(
        name="Перф", slug="p-hid", code_1c="P-HID", category=hidden, status=ProductStatus.IMPORTED
    )
    return p_in, p_zero, p_hid


@pytest.mark.django_db
def test_dry_run_writes_nothing(tmp_path):
    p_in, _z, _h = _catalog()
    call_command("apply_stocks_1c", _write(tmp_path), "--dry-run", "--publish-in-stock")
    p_in.refresh_from_db()
    assert p_in.stock_quantity == 0  # остаток не залит
    assert not p_in.is_visible  # не опубликован
    assert SyncLog.objects.count() == 0


@pytest.mark.django_db
def test_apply_stocks_and_publish_in_stock(tmp_path):
    p_in, p_zero, p_hid = _catalog()
    call_command("apply_stocks_1c", _write(tmp_path), "--publish-in-stock")

    p_in.refresh_from_db()
    p_zero.refresh_from_db()
    p_hid.refresh_from_db()

    # Остатки залиты всем.
    assert p_in.stock_quantity == Decimal("5") and p_in.stock_status == StockStatus.IN_STOCK
    assert p_zero.stock_quantity == Decimal("0")
    assert p_hid.stock_quantity == Decimal("3")

    # Опубликован только товар с остатком И видимой категорией.
    assert p_in.is_visible  # status=published, is_active=True
    assert not p_zero.is_visible  # нулевой остаток → не публикуем
    assert not p_hid.is_visible  # остаток есть, но категория on_site=False
    assert SyncLog.objects.filter(sync_type=SyncLog.SyncType.STOCK).exists()


@pytest.mark.django_db
def test_publish_skipped_without_flag(tmp_path):
    p_in, _z, _h = _catalog()
    call_command("apply_stocks_1c", _write(tmp_path))  # без --publish-in-stock
    p_in.refresh_from_db()
    assert p_in.stock_quantity == Decimal("5")
    assert not p_in.is_visible  # остаток залит, но публикации не было


@pytest.mark.django_db
def test_update_stocks_bulk_chunks_and_skips_unknown():
    # Несколько чанков (chunk=2 на 4 кода) + ненайденный code_1c → skipped.
    p_in, p_zero, p_hid = _catalog()
    items = parse_stock_items(RAW_1C) + [{"code_1c": "NOPE", "stock": "9"}]
    log, result = use_cases.update_stocks_bulk(items, source_file="test", chunk=2)

    p_in.refresh_from_db()
    p_hid.refresh_from_db()
    assert p_in.stock_quantity == Decimal("5") and p_in.stock_status == StockStatus.IN_STOCK
    assert p_hid.stock_quantity == Decimal("3")
    assert result.updated == 3  # P-IN, P-ZERO, P-HID
    assert result.skipped == 1  # NOPE не найден по code_1c
    assert log.result == SyncLog.SyncResult.OK
