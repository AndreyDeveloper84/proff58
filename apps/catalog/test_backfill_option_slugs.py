"""Тесты команды backfill_option_slugs (P2, slug-URL).

Для SELECT-атрибутов (кроме tool_type): создаёт недостающие AttributeOption из
attrs_cache видимых товаров и заполняет ТОЛЬКО пустые slug; непустые не трогает;
уникальность в пределах атрибута; --dry-run без записи.

Wave 7.1/H1: для ``tool_type`` команда options НЕ создаёт — materialization
только через canonical taxonomy manifest + ``load_tool_types`` (guard).
"""

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductStatus,
    StockStatus,
)

ATTR_SLUG = "material"


@pytest.fixture
def leaf(db):
    root = Category.add_root(name="Оснастка", slug="osnastka")
    return root.add_child(name="Расходники", slug="rashodniki")


def make_attr(slug=ATTR_SLUG, atype=AttributeType.SELECT, filterable=True):
    return Attribute.objects.create(
        slug=slug, name=slug, attribute_type=atype, is_filterable=filterable
    )


def make_product(category, slug, attrs, *, status=ProductStatus.PUBLISHED, is_active=True):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        attrs_cache=attrs,
        status=status,
        is_active=is_active,
        stock_status=StockStatus.IN_STOCK,
    )


@pytest.mark.django_db
def test_creates_missing_options_and_fills_slugs(leaf):
    attr = make_attr()
    make_product(leaf, "p1", {ATTR_SLUG: "Коронки"})
    make_product(leaf, "p2", {ATTR_SLUG: "Буры"})

    call_command("backfill_option_slugs")

    opts = {o.value: o.slug for o in attr.options.all()}
    assert opts == {"Коронки": "koronki", "Буры": "bury"}


@pytest.mark.django_db
def test_does_not_overwrite_existing_slug(leaf):
    attr = make_attr()
    AttributeOption.objects.create(attribute=attr, value="Коронки", slug="manual-slug")
    make_product(leaf, "p1", {ATTR_SLUG: "Коронки"})

    call_command("backfill_option_slugs")

    assert attr.options.get(value="Коронки").slug == "manual-slug"  # ручной slug сохранён


@pytest.mark.django_db
def test_collision_gets_suffix(leaf):
    attr = make_attr()
    # Принудим коллизию: slug "koronki" уже занят другой опцией того же атрибута.
    AttributeOption.objects.create(attribute=attr, value="Прочее", slug="koronki")
    make_product(leaf, "p1", {ATTR_SLUG: "Коронки"})

    call_command("backfill_option_slugs")

    assert attr.options.get(value="Коронки").slug == "koronki-2"  # суффикс при коллизии


@pytest.mark.django_db
def test_empty_value_skipped(leaf):
    attr = make_attr()
    make_product(leaf, "p1", {ATTR_SLUG: "   "})  # пустое/пробельное значение
    make_product(leaf, "p2", {ATTR_SLUG: "Коронки"})

    call_command("backfill_option_slugs")

    values = set(attr.options.values_list("value", flat=True))
    assert values == {"Коронки"}  # мусорная опция для "   " не создана


@pytest.mark.django_db
def test_dry_run_writes_nothing(leaf):
    attr = make_attr()
    make_product(leaf, "p1", {ATTR_SLUG: "Коронки"})

    call_command("backfill_option_slugs", "--dry-run")

    assert attr.options.count() == 0  # --dry-run ничего не записал


@pytest.mark.django_db
def test_only_visible_products(leaf):
    attr = make_attr()
    make_product(leaf, "draft", {ATTR_SLUG: "Черновик"}, status=ProductStatus.DRAFT)
    make_product(leaf, "off", {ATTR_SLUG: "Скрытый"}, is_active=False)
    make_product(leaf, "vis", {ATTR_SLUG: "Коронки"})

    call_command("backfill_option_slugs")

    assert set(attr.options.values_list("value", flat=True)) == {"Коронки"}


@pytest.mark.django_db
def test_non_select_attribute_ignored(leaf):
    make_attr(slug="power", atype=AttributeType.INTEGER)
    make_product(leaf, "p1", {"power": 500})

    call_command("backfill_option_slugs")

    assert AttributeOption.objects.count() == 0  # для non-select опции не создаются


@pytest.mark.django_db
def test_tool_type_values_not_created(leaf):
    """Wave 7.1/H1 guard: для tool_type options в runtime не создаются.

    Значение вне canonical manifest — отчёт (outside_manifest), записи в БД нет;
    materialization только через manifest + load_tool_types.
    """
    attr = make_attr(slug="tool_type")
    make_product(leaf, "p1", {"tool_type": "Нестандартное значение вне manifest"})

    call_command("backfill_option_slugs")

    assert attr.options.count() == 0
