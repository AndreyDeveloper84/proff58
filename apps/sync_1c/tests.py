import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import IntegrityError

from apps.catalog.models import (
    Category,
    CategoryMappingRule,
    MappingRuleType,
    Product,
    ProductStatus,
    StockStatus,
)
from apps.sync_1c import importer, parsers
from apps.sync_1c.models import (
    NomenclatureStaging,
    PriceRecord,
    StagingStatus,
    StockRecord,
    SyncLog,
)


@pytest.mark.django_db
def test_staging_created_with_raw_payload():
    record = NomenclatureStaging.objects.create(
        code_1c="000001234",
        article="GSB13-RE",
        raw_payload={"name": "ДРЕЛЬ GSB 13 RE", "price": "4500.00", "qty": "10"},
        name_1c="ДРЕЛЬ GSB 13 RE",
        price=4500.00,
        stock=10,
    )
    assert record.status == StagingStatus.PENDING
    assert record.product is None
    assert record.raw_payload["qty"] == "10"


@pytest.mark.django_db
def test_price_record():
    p = PriceRecord.objects.create(code_1c="000001234", value=4500, price_type="retail")
    assert p.is_current is True
    assert str(p.currency) == "RUB"


@pytest.mark.django_db
def test_stock_record_unique_per_warehouse():
    StockRecord.objects.create(code_1c="000001234", warehouse="main", quantity=10)
    with pytest.raises(IntegrityError):
        StockRecord.objects.create(code_1c="000001234", warehouse="main", quantity=5)


@pytest.mark.django_db
def test_sync_log():
    log = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.PRICES,
        result=SyncLog.SyncResult.OK,
        rows_total=100,
        rows_ok=100,
    )
    assert "Цены" in str(log)


# --- Импортёр с защитой ручной работы ---


@pytest.fixture
def drills_category(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    return root.add_child(name="Дрели", slug="dreli")


@pytest.mark.django_db
def test_import_new_uncategorized_goes_to_review():
    """Новый товар без подходящего правила → «Неразобранные» + needs_review."""
    product, action = importer.import_item(
        {"external_id": "1c-001", "sku": "X-1", "name": "Нечто", "price": "100", "stock": "5"}
    )
    assert action == "created"
    assert product.category is None
    assert product.status == ProductStatus.NEEDS_REVIEW
    assert product.available_quantity == 5
    assert product.stock_status == StockStatus.IN_STOCK


@pytest.mark.django_db
def test_import_new_categorized_becomes_draft(drills_category):
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS, pattern="дрель", target_category=drills_category
    )
    product, _ = importer.import_item(
        {"external_id": "1c-002", "sku": "D-1", "name": "Дрель Bosch", "price": "4500"}
    )
    assert product.category == drills_category
    assert product.status == ProductStatus.DRAFT
    assert product.matched_rule is not None


@pytest.mark.django_db
def test_reimport_does_not_overwrite_manual_content(drills_category):
    """Главное правило: повторный импорт не трогает ручную работу."""
    product, _ = importer.import_item(
        {
            "external_id": "1c-003",
            "sku": "D-2",
            "name": "ДРЕЛЬ ИЗ 1С",
            "price": "1000",
            "stock": "2",
        }
    )
    # Менеджер навёл порядок вручную:
    product.name = "Дрель Bosch GSB 13 RE (витрина)"
    product.category = drills_category
    product.category_is_manual = True
    product.description = "Хорошая дрель"
    product.meta_title = "Купить дрель"
    product.status = ProductStatus.PUBLISHED
    product.save()

    # Повторная выгрузка из 1С с новой ценой/остатком и другим названием:
    importer.import_item(
        {
            "external_id": "1c-003",
            "sku": "D-2",
            "name": "ДРЕЛЬ НОВОЕ ИМЯ 1С",
            "price": "1200",
            "stock": "9",
        }
    )
    product.refresh_from_db()

    # Цена/остаток обновились, original_name обновилось:
    assert product.price == 1200
    assert product.stock_quantity == 9
    assert product.original_name == "ДРЕЛЬ НОВОЕ ИМЯ 1С"
    # А ручной контент НЕ затронут:
    assert product.name == "Дрель Bosch GSB 13 RE (витрина)"
    assert product.category == drills_category
    assert product.description == "Хорошая дрель"
    assert product.meta_title == "Купить дрель"
    assert product.status == ProductStatus.PUBLISHED


@pytest.mark.django_db
def test_import_matches_existing_by_article():
    Product.objects.create(name="Существующий", article="SKU-9", slug="exist-9")
    product, action = importer.import_item({"sku": "SKU-9", "price": "500"})
    assert action == "updated"
    assert product.price == 500


@pytest.mark.django_db
def test_update_price_and_stock_helpers():
    Product.objects.create(name="Т", code_1c="1c-010", slug="t-010")
    assert importer.update_price({"external_id": "1c-010", "price": "999", "old_price": "1200"})
    assert importer.update_stock({"external_id": "1c-010", "stock": "0"})
    p = Product.objects.get(code_1c="1c-010")
    assert p.price == 999
    assert p.old_price == 1200
    assert p.stock_status == StockStatus.OUT_OF_STOCK
    # несуществующий товар:
    assert importer.update_price({"sku": "НЕТ", "price": "1"}) is False


@pytest.mark.django_db
def test_import_items_batch_counts(drills_category):
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS, pattern="дрель", target_category=drills_category
    )
    result = importer.import_items(
        [
            {"external_id": "b-1", "name": "Дрель А", "price": "100"},
            {"external_id": "b-2", "name": "Загадка Б", "price": "200"},
        ]
    )
    assert result.created == 2
    assert result.uncategorized == 1


# --- Инварианты БД и идемпотентность ---


@pytest.mark.django_db
def test_product_code_1c_unique():
    """Дубли code_1c у товаров запрещены на уровне БД."""
    Product.objects.create(name="A", code_1c="dup-1", slug="a-dup")
    with pytest.raises(IntegrityError):
        Product.objects.create(name="B", code_1c="dup-1", slug="b-dup")


@pytest.mark.django_db
def test_only_one_current_price_constraint():
    """Нельзя иметь две актуальные цены на (код, тип, валюта)."""
    PriceRecord.objects.create(code_1c="p-1", price_type="retail", value=100, is_current=True)
    with pytest.raises(IntegrityError):
        PriceRecord.objects.create(code_1c="p-1", price_type="retail", value=120, is_current=True)


@pytest.mark.django_db
def test_reimport_is_idempotent_no_duplicate_products():
    item = {"external_id": "idem-1", "sku": "S-1", "name": "Товар", "price": "100"}
    importer.import_item(item)
    _, action = importer.import_item(item)
    assert action == "updated"
    assert Product.objects.filter(code_1c="idem-1").count() == 1


@pytest.mark.django_db
def test_price_history_keeps_single_current():
    """Повторное обновление цены: история растёт, актуальная одна."""
    Product.objects.create(name="Т", code_1c="ph-1", slug="ph-1")
    importer.update_price({"external_id": "ph-1", "price": "100"})
    importer.update_price({"external_id": "ph-1", "price": "150"})
    records = PriceRecord.objects.filter(code_1c="ph-1", price_type="retail")
    assert records.count() == 2
    current = records.filter(is_current=True)
    assert current.count() == 1
    assert current.first().value == 150


@pytest.mark.django_db
def test_run_import_links_rows_to_sync_log():
    sync_log, result = importer.run_import(
        [
            {"external_id": "r-1", "name": "Раз", "price": "10"},
            {"external_id": "r-2", "name": "Два", "price": "20"},
        ],
        source_file="test.json",
    )
    assert sync_log.rows_total == 2
    assert sync_log.rows_ok == 2
    assert sync_log.source_file == "test.json"
    # все staging-строки привязаны к прогону и имеют хэш
    rows = sync_log.rows.all()
    assert rows.count() == 2
    assert all(r.row_hash for r in rows)


@pytest.mark.django_db
def test_management_command_imports_json(tmp_path):
    f = tmp_path / "nomenclature.json"
    f.write_text(
        json.dumps(
            {
                "items": [
                    {"external_id": "cmd-1", "sku": "C-1", "name": "Файл-товар", "price": "999"}
                ]
            }
        ),
        encoding="utf-8",
    )
    call_command("import_1c", str(f))
    p = Product.objects.get(code_1c="cmd-1")
    assert p.price == 999
    assert NomenclatureStaging.objects.filter(code_1c="cmd-1").exists()


@pytest.mark.django_db
def test_management_command_imports_bundled_sample():
    """Пример выгрузки apps/sync_1c/sample_data/ остаётся валидным и импортируется."""
    sample = Path(__file__).resolve().parent / "sample_data" / "nomenclature_sample.json"
    assert sample.exists()
    call_command("import_1c", str(sample))
    # три товара из примера: один без бренда уходит в «Неразобранные»
    assert Product.objects.filter(code_1c="1c-000123").exists()
    assert Product.objects.get(code_1c="1c-000777").stock_status == StockStatus.OUT_OF_STOCK
    assert Product.objects.get(code_1c="1c-000999").category is None


@pytest.mark.django_db
def test_ambiguous_article_goes_to_conflict():
    """Артикул не уникален: если по нему подходит >1 товара — конфликт, не порча данных."""
    Product.objects.create(name="Товар 1", article="DUP-ART", slug="t1-dup", price=10)
    Product.objects.create(name="Товар 2", article="DUP-ART", slug="t2-dup", price=20)
    # импорт без code_1c, только по артикулу
    product, action = importer.import_item({"sku": "DUP-ART", "price": "999"})
    assert action == "conflict"
    assert product is None
    # ни один товар не изменён
    assert {float(p.price) for p in Product.objects.filter(article="DUP-ART")} == {10.0, 20.0}
    staging = NomenclatureStaging.objects.filter(article="DUP-ART").latest("imported_at")
    assert staging.status == StagingStatus.ERROR
    assert "Неоднозначный" in staging.error_message


@pytest.mark.django_db
def test_parser_rejects_unknown_format(tmp_path):
    f = tmp_path / "data.xml"
    f.write_text("<x/>", encoding="utf-8")
    with pytest.raises(ValueError):
        parsers.load_items(str(f))
