import pytest

from apps.catalog.models import (
    Category,
    CategoryMappingRule,
    MappingRuleType,
    Product,
    ProductStatus,
    StockStatus,
)
from apps.sync_1c import importer
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
    from django.db import IntegrityError

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
