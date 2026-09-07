"""Тесты уборки привязок характеристик (DRF-1428, A1/A3).

Команда пишет в каталог, поэтому проверяем не «что-то произошло», а границы: что
она НЕ трогает, что откат возвращает ровно снятое и что повторный прогон
ничего не делает.
"""

import io
import json
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
    StockStatus,
)


def run(*args, **kwargs):
    out = io.StringIO()
    call_command("catalog_cleanup_bindings", *args, stdout=out, **kwargs)
    return out.getvalue()


@pytest.fixture
def setup(db):
    live_root = Category.add_root(name="Электроинструмент", slug="ei")
    leaf = live_root.add_child(name="Дрели", slug="dreli")
    dead_root = Category.add_root(name="Легаси", slug="legacy", on_site=False)
    chuck = Attribute.objects.create(
        slug="chuck", name="Патрон", attribute_type=AttributeType.TEXT, is_filterable=True
    )
    CategoryAttribute.objects.create(category=leaf, attribute=chuck)
    CategoryAttribute.objects.create(category=dead_root, attribute=chuck)  # мёртвый дубль
    return live_root, leaf, dead_root, chuck


def test_dry_run_ничего_не_пишет(setup):
    before = CategoryAttribute.objects.count()

    output = run()

    assert "DRY-RUN" in output
    assert CategoryAttribute.objects.count() == before


def test_мёртвая_привязка_снимается_а_живая_остаётся(setup):
    _root, leaf, dead_root, chuck = setup

    run("--commit")

    assert not CategoryAttribute.objects.filter(category=dead_root).exists()
    assert CategoryAttribute.objects.filter(category=leaf, attribute=chuck).exists()


def test_последняя_привязка_атрибута_не_снимается(setup):
    """Снять единственную привязку — не убрать мусор, а потерять фасет."""
    _root, _leaf, dead_root, _chuck = setup
    only_dead = Attribute.objects.create(
        slug="bore", name="Посадка", attribute_type=AttributeType.TEXT, is_filterable=True
    )
    CategoryAttribute.objects.create(category=dead_root, attribute=only_dead)

    output = run("--commit")

    assert CategoryAttribute.objects.filter(attribute=only_dead).exists()
    assert "ОСТАВЛЕНО" in output


def test_бесхозный_атрибут_привязывается_без_фильтра(setup):
    _root, leaf, _dead, _chuck = setup
    orphan = Attribute.objects.create(
        slug="lift_height",
        name="Высота подъёма",
        attribute_type=AttributeType.INTEGER,
        is_filterable=False,
    )
    product = Product.objects.create(
        category=leaf,
        name="Домкрат",
        slug="jack",
        status=ProductStatus.PUBLISHED,
        stock_status=StockStatus.IN_STOCK,
        stock_quantity=1,
    )
    ProductAttributeValue.objects.create(product=product, attribute=orphan, value_integer=300)

    run("--commit")

    binding = CategoryAttribute.objects.get(attribute=orphan)
    # Характеристика возвращается на карточку, но в сайдбар не лезет: у неё
    # значения лишь у горстки товаров, фасет был бы шумом.
    assert binding.category_id == leaf.id
    assert binding.is_filter is False


def test_бесхозный_атрибут_из_разных_категорий_остаётся_куратору(setup):
    _root, leaf, dead_root, _chuck = setup
    other = leaf.get_root().add_child(name="Перфораторы", slug="perf")
    spread = Attribute.objects.create(
        slug="weight_kg", name="Масса", attribute_type=AttributeType.DECIMAL, is_filterable=False
    )
    for i, cat in enumerate((leaf, other)):
        product = Product.objects.create(
            category=cat,
            name=f"t{i}",
            slug=f"t{i}",
            status=ProductStatus.PUBLISHED,
        )
        ProductAttributeValue.objects.create(product=product, attribute=spread, value_decimal=1)

    output = run("--commit")

    assert not CategoryAttribute.objects.filter(attribute=spread).exists()
    assert "ПРОПУЩЕН" in output


def test_откат_возвращает_снятое(setup, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    _root, _leaf, dead_root, chuck = setup

    run("--commit")
    snapshot = next((tmp_path / "var" / "restructure").glob("cleanup-bindings-*.json"))
    run(rollback=str(snapshot))

    assert CategoryAttribute.objects.filter(category=dead_root, attribute=chuck).exists()
    assert json.loads(Path(snapshot).read_text(encoding="utf-8"))["removed"]


def test_повторный_прогон_идемпотентен(setup):
    run("--commit")

    output = run()

    assert "Чисто: убирать нечего." in output
