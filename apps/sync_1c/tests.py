import json
from pathlib import Path
from unittest import mock

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
from apps.sync_1c import importer, normalizers, parsers, product_writer, use_cases
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


# --- Characterization-тесты новых контрактов (после рефакторинга) ---


@pytest.mark.django_db
def test_update_products_does_not_create():
    """update_products (create_missing=False): отсутствующий товар → skipped, не создаётся."""
    sync_log, result = use_cases.update_products(
        [{"external_id": "u-1", "name": "Новый", "price": "100"}]
    )
    assert result.created == 0
    assert result.skipped == 1
    assert Product.objects.filter(code_1c="u-1").count() == 0
    assert sync_log.rows_ok == 1  # skipped — не ошибка


@pytest.mark.django_db
def test_command_update_only_does_not_create(tmp_path):
    f = tmp_path / "n.json"
    f.write_text(json.dumps({"items": [{"external_id": "uo-1", "name": "Х", "price": "1"}]}))
    call_command("import_1c", str(f), "--update-only")
    assert Product.objects.filter(code_1c="uo-1").count() == 0
    staging = NomenclatureStaging.objects.filter(code_1c="uo-1").latest("imported_at")
    assert staging.status == StagingStatus.SKIPPED


@pytest.mark.django_db
def test_cp1251_csv_with_russian_headers(tmp_path):
    f = tmp_path / "vygruzka.csv"
    content = "Код;Артикул;Наименование;Цена;Остаток\r\n" "1c-cp;BOSCH-1;Дрель Бош;5900,50;7\r\n"
    f.write_bytes(content.encode("cp1251"))
    sync_log, result = use_cases.import_products(parsers.load_items(str(f)), source_file=str(f))
    assert result.created == 1
    p = Product.objects.get(code_1c="1c-cp")
    assert p.original_name == "Дрель Бош"
    assert p.article == "BOSCH-1"
    assert str(p.price) == "5900.50"  # запятая 1С → точка


@pytest.mark.django_db
def test_duplicate_names_get_unique_slugs():
    """Дубликаты имён в 1С → уникальные slug, ни одна строка не теряется."""
    # уже есть товар со slug "дрель" — импорт не должен на него натыкаться
    Product.objects.create(name="Дрель", slug="дрель", code_1c="exist-1")
    sync_log, result = use_cases.import_products(
        [
            {"external_id": "dup-1", "name": "Дрель", "price": "100"},
            {"external_id": "dup-2", "name": "Дрель", "price": "200"},
            {"external_id": "ok-1", "name": "Молоток", "price": "300"},
        ]
    )
    assert result.created == 3 and result.errors == 0
    # Инвариант — УНИКАЛЬНОСТЬ slug (не точный суффикс): bulk использует стабильный
    # «{base}-{code_1c}» при коллизии, одиночный путь — числовой суффикс.
    slugs = {Product.objects.get(code_1c=c).slug for c in ("dup-1", "dup-2", "ok-1", "exist-1")}
    assert len(slugs) == 4  # все уникальны, ни одна строка не потеряна
    for c in ("dup-1", "dup-2"):
        assert Product.objects.get(code_1c=c).slug.startswith("дрель")  # база сохранена
    assert Product.objects.get(code_1c="ok-1").slug == "молоток"
    assert Product.objects.filter(slug="дрель").count() == 1  # существующий не тронут


@pytest.mark.django_db
def test_bad_row_recorded_and_batch_continues():
    """Сбой обработки одной строки → staging.ERROR + SyncLog.error_details, остальные ок.

    В bulk-пути запись товара собирается через build_new_product — туда и инжектим сбой;
    классификация строки изолирована (partial-failure), батч продолжается.
    """
    original = product_writer.build_new_product

    def side_effect(item, **kwargs):
        if item.code_1c == "bad-1":
            raise RuntimeError("boom bad-1")
        return original(item, **kwargs)

    with mock.patch("apps.sync_1c.product_writer.build_new_product", side_effect=side_effect):
        sync_log, result = use_cases.import_products(
            [
                {"external_id": "ok-1", "name": "Молоток", "price": "100"},
                {"external_id": "bad-1", "name": "Дрель", "price": "200"},  # сбой обработки
                {"external_id": "ok-2", "name": "Пила", "price": "300"},
            ]
        )
    assert result.created == 2
    assert result.errors == 1
    assert "bad-1" in sync_log.error_details
    bad = NomenclatureStaging.objects.filter(code_1c="bad-1").latest("imported_at")
    assert bad.status == StagingStatus.ERROR
    assert bad.error_message  # причина сохранена


@pytest.mark.django_db
def test_prices_update_ambiguous_article_is_error_not_silent():
    """update_prices при неоднозначном артикуле не обновляет случайный товар."""
    Product.objects.create(name="Т1", article="AMB", slug="amb-1", price=10)
    Product.objects.create(name="Т2", article="AMB", slug="amb-2", price=20)
    sync_log, result = use_cases.update_prices([{"sku": "AMB", "price": "999"}])
    assert result.updated == 0
    assert result.errors == 1
    assert {float(p.price) for p in Product.objects.filter(article="AMB")} == {10.0, 20.0}
    assert "AMB" in sync_log.error_details


@pytest.mark.django_db
def test_normalize_item_aliases_and_decimal():
    item = normalizers.normalize_item(
        {"Код": "k1", "Артикул": "a1", "Цена": "1 234,50", "Активность": "да"}
    )
    assert item.code_1c == "k1"
    assert item.article == "a1"
    assert str(item.price) == "1234.50"
    assert item.is_active is True
