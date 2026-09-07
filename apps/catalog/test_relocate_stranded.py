"""Тесты переноса застрявших товаров в живое дерево (DRF-1438).

Команда двигает товары по каталогу, поэтому тесты держат прежде всего её отказы:
куда она НЕ переносит и что оставляет человеку. Автоматический перенос в неверный
лист хуже, чем товар, до которого не дойти, — ошибку потом ищут глазами по всему дереву.
"""

import io

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    StockStatus,
)
from apps.catalog.relocate import build_plan


@pytest.fixture
def tree(db):
    live = Category.add_root(name="Измерительный инструмент", slug="izmeritelnyy")
    leaf = live.add_child(name="Рулетки", slug="ruletki")
    other = live.add_child(name="Лампы", slug="lampy")
    dead = Category.add_root(name="Легаси", slug="legacy", is_active=False, on_site=False)
    attribute = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    return live, leaf, other, dead, attribute


def option(attribute, value, slug):
    return AttributeOption.objects.create(attribute=attribute, value=value, slug=slug)


def product(category, name, *, stock=5, status=ProductStatus.PUBLISHED, active=True):
    return Product.objects.create(
        category=category,
        name=name,
        slug=name,
        status=status,
        is_active=active,
        stock_status=StockStatus.IN_STOCK if stock else StockStatus.OUT_OF_STOCK,
        stock_quantity=stock,
    )


def set_type(prod, attribute, opt):
    ProductAttributeValue.objects.create(product=prod, attribute=attribute, value_option=opt)


def run(*args, **kwargs):
    out = io.StringIO()
    call_command("catalog_relocate_stranded", *args, stdout=out, **kwargs)
    return out.getvalue()


def test_в_пул_попадает_только_живой_товар_вне_дерева(tree):
    _live, leaf, _other, dead, attr = tree
    stuck = product(dead, "застрявший")
    product(dead, "без-остатка", stock=0)
    product(dead, "снятый", status=ProductStatus.DRAFT)
    product(leaf, "нормальный")
    ruletka = option(attr, "Рулетки", "ruletki")
    for i in range(4):
        set_type(product(leaf, f"живая-рулетка-{i}"), attr, ruletka)
    set_type(stuck, attr, ruletka)

    plan = build_plan()

    assert plan.pool_size == 1
    assert [m.product.id for m in plan.moves] == [stuck.id]
    assert plan.moves[0].target.slug == "ruletki"


def test_тип_чужой_для_листа_уходит_на_сверку(tree):
    """Шесть паяльников по недосмотру в «Лампах» не повод отправить туда весь тип."""
    _live, _leaf, other, dead, attr = tree
    solder = option(attr, "Паяльники", "payalniki")
    lamp = option(attr, "Лампы", "lampy")
    for i in range(30):
        set_type(product(other, f"лампа-{i}"), attr, lamp)
    for i in range(3):
        set_type(product(other, f"паяльник-{i}"), attr, solder)
    stuck = product(dead, "паяльник-застрявший")
    set_type(stuck, attr, solder)

    plan = build_plan()

    assert plan.moves == []
    assert [m.product.id for m in plan.needs_review] == [stuck.id]
    assert plan.needs_review[0].leaf_main_type[0] == "Лампы"


def test_тип_размазан_по_дереву_остаётся_без_решения(tree):
    live, leaf, other, dead, attr = tree
    third = live.add_child(name="Уровни", slug="urovni")
    opt = option(attr, "Спорный", "sporny")
    for target in (leaf, other, third):
        for i in range(4):
            set_type(product(target, f"{target.slug}-{i}"), attr, opt)
    set_type(product(dead, "застрявший"), attr, opt)

    plan = build_plan()

    assert plan.moves == []
    assert plan.unresolved and "размазан" in plan.unresolved[0][3]


def test_типа_нет_в_живом_дереве_остаётся_без_решения(tree):
    _live, _leaf, _other, dead, attr = tree
    opt = option(attr, "Одинокий", "odinoky")
    set_type(product(dead, "застрявший"), attr, opt)

    plan = build_plan()

    assert plan.moves == []
    assert plan.unresolved[0][3] == "живых товаров этого типа в дереве нет"


def test_товар_без_типа_не_переносится(tree):
    _live, _leaf, _other, dead, _attr = tree
    stuck = product(dead, "без-типа")

    plan = build_plan()

    # Тип определяет и фильтры, и панель навигации — подставлять его ради переноса нельзя.
    assert [p.id for p in plan.no_type] == [stuck.id]
    assert plan.moves == []


def test_перенос_ставит_ручную_категорию(tree):
    _live, leaf, _other, dead, attr = tree
    ruletka = option(attr, "Рулетки", "ruletki")
    for i in range(4):
        set_type(product(leaf, f"живая-{i}"), attr, ruletka)
    stuck = product(dead, "застрявший")
    set_type(stuck, attr, ruletka)

    run("--commit")

    stuck.refresh_from_db()
    assert stuck.category_id == leaf.id
    # Без ручного флага следующая автокатегоризация утащит товар обратно.
    assert stuck.category_is_manual is True


def test_откат_возвращает_прежнюю_категорию(tree, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    _live, leaf, _other, dead, attr = tree
    ruletka = option(attr, "Рулетки", "ruletki")
    for i in range(4):
        set_type(product(leaf, f"живая-{i}"), attr, ruletka)
    stuck = product(dead, "застрявший")
    set_type(stuck, attr, ruletka)
    run("--commit")
    snapshot = next((tmp_path / "var" / "restructure").glob("relocate-stranded-*.json"))

    run(rollback=str(snapshot))

    stuck.refresh_from_db()
    assert stuck.category_id == dead.id
    assert stuck.category_is_manual is False


def test_повторный_прогон_даёт_пустой_план(tree):
    _live, leaf, _other, dead, attr = tree
    ruletka = option(attr, "Рулетки", "ruletki")
    for i in range(4):
        set_type(product(leaf, f"живая-{i}"), attr, ruletka)
    set_type(product(dead, "застрявший"), attr, ruletka)
    run("--commit")

    output = run()

    assert "Переносить нечего." in output


def test_dry_run_ничего_не_двигает(tree):
    _live, leaf, _other, dead, attr = tree
    ruletka = option(attr, "Рулетки", "ruletki")
    for i in range(4):
        set_type(product(leaf, f"живая-{i}"), attr, ruletka)
    stuck = product(dead, "застрявший")
    set_type(stuck, attr, ruletka)

    output = run()

    stuck.refresh_from_db()
    assert stuck.category_id == dead.id
    assert "DRY-RUN" in output
