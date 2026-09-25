"""Граница выборки ``enrich_attributes`` (окно ХАР-SCOPE).

Проверяем новые флаги ``--tool-type`` / ``--category-id`` / ``--include-descendants``
/ ``--in-stock-only`` / ``--active-only``:

- ``--in-stock-only`` выкидывает товары с нулевым остатком;
- ``--active-only`` выкидывает товары с ``is_active=False``;
- ``--category-id`` не захватывает соседнюю ветку дерева;
- ``--include-descendants`` берёт 93 «Метчики» и 94 «Плашки» через родителя 92;
- фильтры складываются пересечением (AND), а не альтернативами;
- dry-run и боевой apply выбирают ОДИН И ТОТ ЖЕ набор ``product_id``;
- без новых флагов поведение команды прежнее (обратная совместимость).

Дерево фикстуры повторяет боевое (ХАР-BIND, решение владельца «метчики на 92»):
92 «Металлорежущий инструмент» → 93 «Метчики», 94 «Плашки»; 95 — соседняя ветка.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    Source,
)

# Типы с блоками правил в data/attribute_rules.json: у обоих есть regex-атрибут,
# поэтому каждый товар фикстуры даёт хотя бы одну строку отчёта.
DRILL = "dreli-shurupoverty"
HAMMER = "molotki"

DRILL_NAME = "Дрель-шуруповёрт аккумуляторный 18В"
HAMMER_NAME = "Молоток слесарный 500 г"


@pytest.fixture
def tree(db):
    """Категории 92 → (93, 94) и соседняя ветка 95 + опции tool_type."""
    top = Category.add_root(
        pk=92, name="Металлорежущий инструмент", slug="metallorezhushchiy", on_site=True
    )
    metchiki = top.add_child(pk=93, name="Метчики", slug="metchiki-cat", on_site=True)
    plashki = top.add_child(pk=94, name="Плашки", slug="plashki-cat", on_site=True)
    other = Category.add_root(pk=95, name="Ручной инструмент", slug="ruchnoy", on_site=True)

    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    options = {
        DRILL: AttributeOption.objects.create(
            attribute=tool_type, value="Дрели и шуруповёрты", slug=DRILL
        ),
        HAMMER: AttributeOption.objects.create(attribute=tool_type, value="Молотки", slug=HAMMER),
    }
    return {
        "top": top,
        "metchiki": metchiki,
        "plashki": plashki,
        "other": other,
        "tool_type": tool_type,
        "options": options,
    }


def _make_product(tree, category, code, *, tool_type=DRILL, stock="5", is_active=False):
    """Товар в категории с проставленным tool_type (как после enrich_tool_type).

    ``is_active`` по умолчанию False — как у модели ``Product``.
    """
    name = DRILL_NAME if tool_type == DRILL else HAMMER_NAME
    product = Product.objects.create(
        category=category,
        name=f"{name} {code}",
        slug=code,
        code_1c=code,
        available_quantity=Decimal(stock),
        is_active=is_active,
    )
    ProductAttributeValue.objects.create(
        product=product,
        attribute=tree["tool_type"],
        value_option=tree["options"][tool_type],
        source=Source.MANUAL,
    )
    return product


def _dry_run(*args):
    """enrich_attributes --dry-run с произвольными флагами → распарсенный JSON."""
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--dry-run", *args, stdout=out, stderr=err)
    return json.loads(out.getvalue())


def _selected(report):
    """Набор product_id, попавших в выборку прогона."""
    return {row["product_id"] for row in report["rows"]}


# --- 1. остаток -----------------------------------------------------------


@pytest.mark.django_db
def test_in_stock_only_excludes_zero_stock(tree):
    in_stock = _make_product(tree, tree["metchiki"], "s-in", stock="5")
    _make_product(tree, tree["metchiki"], "s-out", stock="0")
    call_command("load_attributes")

    report = _dry_run("--in-stock-only")

    assert report["scope"]["in_stock_only"] is True
    assert report["scope"]["selected_products"] == 1
    assert report["totals"]["processed"] == 1
    assert _selected(report) == {in_stock.id}


@pytest.mark.django_db
def test_without_in_stock_only_zero_stock_still_selected(tree):
    """Флаг по умолчанию выключен: нулевой остаток из выборки не выпадает."""
    in_stock = _make_product(tree, tree["metchiki"], "z-in", stock="5")
    out_of_stock = _make_product(tree, tree["metchiki"], "z-out", stock="0")
    call_command("load_attributes")

    report = _dry_run()

    assert _selected(report) == {in_stock.id, out_of_stock.id}


# --- 1b. активность ---------------------------------------------------------


@pytest.mark.django_db
def test_active_only_excludes_inactive_products(tree):
    active = _make_product(tree, tree["metchiki"], "act-on", is_active=True)
    _make_product(tree, tree["metchiki"], "act-off", is_active=False)
    call_command("load_attributes")

    report = _dry_run("--active-only")

    assert report["scope"]["active_only"] is True
    assert report["scope"]["selected_products"] == 1
    assert report["totals"]["processed"] == 1
    assert _selected(report) == {active.id}


@pytest.mark.django_db
def test_without_active_only_inactive_still_selected(tree):
    """Флаг по умолчанию выключен: неактивный товар из выборки не выпадает."""
    active = _make_product(tree, tree["metchiki"], "act-in", is_active=True)
    inactive = _make_product(tree, tree["metchiki"], "act-out", is_active=False)
    call_command("load_attributes")

    report = _dry_run()

    assert report["scope"]["active_only"] is False
    assert _selected(report) == {active.id, inactive.id}


# --- 2. категория: соседняя ветка ------------------------------------------


@pytest.mark.django_db
def test_category_id_does_not_capture_sibling_branch(tree):
    mine = _make_product(tree, tree["metchiki"], "c-mine")
    _make_product(tree, tree["other"], "c-alien")
    call_command("load_attributes")

    report = _dry_run("--category-id", "93")

    assert report["scope"]["resolved_category_ids"] == [93]
    assert _selected(report) == {mine.id}


@pytest.mark.django_db
def test_category_id_without_descendants_takes_only_the_node(tree):
    """Без --include-descendants берём ровно указанный узел, потомков — нет."""
    on_node = _make_product(tree, tree["top"], "n-92")
    _make_product(tree, tree["metchiki"], "n-93")
    call_command("load_attributes")

    report = _dry_run("--category-id", "92")

    assert report["scope"]["resolved_category_ids"] == [92]
    assert _selected(report) == {on_node.id}


@pytest.mark.django_db
def test_unknown_category_id_is_an_error(tree):
    """Опечатка в id — ошибка, а не молча пустая выборка."""
    _make_product(tree, tree["metchiki"], "e-1")
    call_command("load_attributes")

    with pytest.raises(CommandError, match="9999"):
        call_command("enrich_attributes", "--dry-run", "--category-id", "9999", stdout=StringIO())


@pytest.mark.django_db
def test_include_descendants_requires_category(tree):
    call_command("load_attributes")

    with pytest.raises(CommandError, match="--category-id"):
        call_command("enrich_attributes", "--dry-run", "--include-descendants", stdout=StringIO())


# --- 3. потомки 93 и 94 через родителя 92 -----------------------------------


@pytest.mark.django_db
def test_include_descendants_covers_93_and_94(tree):
    on_92 = _make_product(tree, tree["top"], "d-92")
    on_93 = _make_product(tree, tree["metchiki"], "d-93")
    on_94 = _make_product(tree, tree["plashki"], "d-94")
    _make_product(tree, tree["other"], "d-95")
    call_command("load_attributes")

    report = _dry_run("--category-id", "92", "--include-descendants")

    assert report["scope"]["resolved_category_ids"] == [92, 93, 94]
    assert _selected(report) == {on_92.id, on_93.id, on_94.id}


# --- 4. пересечение (AND) ---------------------------------------------------


@pytest.mark.django_db
def test_filters_combine_as_and(tree):
    """Только: нужный тип И внутри ветки 92 И с ненулевым остатком."""
    target = _make_product(tree, tree["metchiki"], "and-ok", tool_type=DRILL, stock="7")
    # каждый следующий нарушает ровно одно условие
    _make_product(tree, tree["metchiki"], "and-type", tool_type=HAMMER, stock="7")
    _make_product(tree, tree["other"], "and-branch", tool_type=DRILL, stock="7")
    _make_product(tree, tree["plashki"], "and-stock", tool_type=DRILL, stock="0")
    call_command("load_attributes")

    report = _dry_run(
        "--tool-type",
        DRILL,
        "--category-id",
        "92",
        "--include-descendants",
        "--in-stock-only",
    )

    assert report["scope"]["selected_products"] == 1
    assert _selected(report) == {target.id}


@pytest.mark.django_db
def test_active_only_joins_the_and_with_other_filters(tree):
    """Активность — ещё одно И: тип И ветка 92 И остаток И is_active."""
    target = _make_product(
        tree, tree["metchiki"], "aa-ok", tool_type=DRILL, stock="7", is_active=True
    )
    # каждый следующий нарушает ровно одно условие
    _make_product(tree, tree["metchiki"], "aa-active", tool_type=DRILL, stock="7", is_active=False)
    _make_product(tree, tree["metchiki"], "aa-type", tool_type=HAMMER, stock="7", is_active=True)
    _make_product(tree, tree["other"], "aa-branch", tool_type=DRILL, stock="7", is_active=True)
    _make_product(tree, tree["plashki"], "aa-stock", tool_type=DRILL, stock="0", is_active=True)
    call_command("load_attributes")

    report = _dry_run(
        "--tool-type",
        DRILL,
        "--category-id",
        "92",
        "--include-descendants",
        "--in-stock-only",
        "--active-only",
    )

    assert report["scope"]["selected_products"] == 1
    assert _selected(report) == {target.id}


@pytest.mark.django_db
def test_repeatable_tool_type_is_a_union_inside_the_and(tree):
    """Несколько --tool-type — объединение по типу, но всё равно И по ветке/остатку."""
    drill = _make_product(tree, tree["metchiki"], "u-drill", tool_type=DRILL)
    hammer = _make_product(tree, tree["plashki"], "u-hammer", tool_type=HAMMER)
    _make_product(tree, tree["other"], "u-alien", tool_type=HAMMER)
    call_command("load_attributes")

    report = _dry_run(
        "--tool-type", DRILL, "--tool-type", HAMMER, "--category-id", "92", "--include-descendants"
    )

    assert report["scope"]["selected_tool_types"] == sorted([DRILL, HAMMER])
    assert _selected(report) == {drill.id, hammer.id}


@pytest.mark.django_db
def test_tool_type_without_rules_warns_and_selects_nothing(tree):
    """Тип есть в манифесте, но блока правил нет — предупреждение, не падение."""
    _make_product(tree, tree["metchiki"], "w-1")
    call_command("load_attributes")

    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--dry-run", "--tool-type", "plashki", stdout=out, stderr=err)
    report = json.loads(out.getvalue())

    assert "plashki" in err.getvalue()
    assert report["scope"]["selected_products"] == 0
    assert report["rows"] == []


# --- 5. dry-run и apply берут один и тот же набор ---------------------------


@pytest.mark.django_db
def test_dry_run_and_apply_select_the_same_products(tree):
    """Ключевое: скоуп применяется до расхождения режимов."""
    _make_product(tree, tree["metchiki"], "e-93", stock="3")
    _make_product(tree, tree["plashki"], "e-94", stock="4")
    _make_product(tree, tree["plashki"], "e-94-zero", stock="0")
    _make_product(tree, tree["other"], "e-95", stock="9")
    call_command("load_attributes")

    scope = [
        "--tool-type",
        DRILL,
        "--category-id",
        "92",
        "--include-descendants",
        "--in-stock-only",
    ]

    report = _dry_run(*scope)
    dry_run_ids = _selected(report)

    before = set(ProductAttributeValue.objects.values_list("product_id", "attribute__slug"))
    call_command("enrich_attributes", *scope, stdout=StringIO(), stderr=StringIO())
    after = set(ProductAttributeValue.objects.values_list("product_id", "attribute__slug"))

    touched = {product_id for product_id, _slug in after - before}
    assert touched == dry_run_ids, "apply тронул не тот набор товаров, что показал dry-run"
    assert report["scope"]["selected_products"] == len(dry_run_ids)

    # Товары вне скоупа не получили ни одной характеристики.
    out_of_scope = Product.objects.exclude(id__in=dry_run_ids)
    for product in out_of_scope:
        assert not product.attribute_values.exclude(attribute__slug="tool_type").exists()
        assert product.attrs_cache == {}


@pytest.mark.django_db
def test_active_only_dry_run_and_apply_select_the_same_products(tree):
    """С --active-only оба режима берут один и тот же набор product_id."""
    _make_product(tree, tree["metchiki"], "ae-93", is_active=True)
    _make_product(tree, tree["plashki"], "ae-94", is_active=True)
    _make_product(tree, tree["plashki"], "ae-94-off", is_active=False)
    _make_product(tree, tree["other"], "ae-95", is_active=False)
    call_command("load_attributes")

    scope = ["--active-only"]

    report = _dry_run(*scope)
    dry_run_ids = _selected(report)

    before = set(ProductAttributeValue.objects.values_list("product_id", "attribute__slug"))
    call_command("enrich_attributes", *scope, stdout=StringIO(), stderr=StringIO())
    after = set(ProductAttributeValue.objects.values_list("product_id", "attribute__slug"))

    touched = {product_id for product_id, _slug in after - before}
    assert touched == dry_run_ids, "apply тронул не тот набор товаров, что показал dry-run"
    assert report["scope"]["selected_products"] == len(dry_run_ids)

    # Неактивные товары не получили ни одной характеристики.
    for product in Product.objects.exclude(id__in=dry_run_ids):
        assert not product.attribute_values.exclude(attribute__slug="tool_type").exists()
        assert product.attrs_cache == {}


# --- 6. обратная совместимость ---------------------------------------------


@pytest.mark.django_db
def test_no_new_flags_keeps_previous_selection(tree):
    """Без новых флагов выбираются все товары типов, описанных правилами."""
    expected = {
        _make_product(tree, tree["top"], "b-92").id,
        _make_product(tree, tree["metchiki"], "b-93", stock="0").id,
        _make_product(tree, tree["plashki"], "b-94", tool_type=HAMMER).id,
        _make_product(tree, tree["other"], "b-95", is_active=True).id,
    }
    call_command("load_attributes")

    report = _dry_run()

    assert _selected(report) == expected
    assert report["totals"]["processed"] == len(expected)
    assert report["scope"] == {
        "tool_types": [],
        "category_ids": [],
        "include_descendants": False,
        "in_stock_only": False,
        "active_only": False,
        "resolved_category_ids": [],
        "selected_tool_types": report["scope"]["selected_tool_types"],
        "selected_products": len(expected),
    }


@pytest.mark.django_db
def test_apply_without_new_flags_writes_everything(tree):
    """Боевой режим без флагов не сузился: пишет всем, включая нулевой остаток."""
    zero = _make_product(tree, tree["metchiki"], "a-zero", stock="0", is_active=True)
    alien = _make_product(tree, tree["other"], "a-alien", is_active=False)
    call_command("load_attributes")

    call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    for product in (zero, alien):
        assert ProductAttributeValue.objects.filter(
            product=product, attribute__slug="voltage"
        ).exists()
