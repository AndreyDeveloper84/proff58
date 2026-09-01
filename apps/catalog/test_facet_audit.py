"""Тесты аудита фильтров каталога (DRF-1428).

Аудит — измерительный прибор: если он врёт, врут и выводы о каталоге. Поэтому
проверяем не «команда отработала», а что каждая метрика отличает случай, ради
которого её завели: выключенный предок прячет поддерево, привязка без данных
сайдбара не делает, расхождение счётчиков роняет команду.
"""

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.facet_audit import (
    audit_bindings,
    audit_sidebars,
    check_circle,
    visible_categories,
    visible_leaves,
)
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductStatus,
    StockStatus,
)


def make_product(category, slug, attrs, *, stock=5):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        attrs_cache=attrs,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=StockStatus.IN_STOCK,
        stock_quantity=stock,
    )


@pytest.fixture
def tree(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    leaf = root.add_child(name="Дрели", slug="dreli")
    attr = Attribute.objects.create(
        slug="chuck", name="Патрон", attribute_type=AttributeType.TEXT, is_filterable=True
    )
    CategoryAttribute.objects.create(category=root, attribute=attr)
    return root, leaf, attr


def test_выключенный_предок_прячет_поддерево(tree):
    root, leaf, _ = tree
    assert leaf in visible_categories()

    root.on_site = False
    root.save()

    # Сам лист остался активным — но покупатель до него не дойдёт, и мерить его
    # сайдбар бессмысленно: страницы фактически нет.
    assert visible_categories() == []


def test_лист_это_категория_без_видимых_детей(tree):
    root, leaf, _ = tree
    hidden = root.add_child(name="Скрытая", slug="hidden", on_site=False)
    assert hidden not in visible_categories()

    leaves = visible_leaves()

    assert [c.slug for c in leaves] == ["dreli"]


def test_привязка_без_данных_сайдбара_не_даёт(tree):
    root, leaf, _ = tree
    make_product(leaf, "d1", {})
    make_product(leaf, "d2", {})

    report = audit_sidebars([leaf])[0]

    # Атрибут привязан и наследуется, но значений у товаров нет — покупатель
    # видит пустой сайдбар. Отчёт обязан называть это «нечем фильтровать».
    assert report.usable_facets == []
    assert not report.has_sidebar
    assert report.unbound_axes == []


def test_одно_значение_фасетом_не_считается(tree):
    root, leaf, _ = tree
    make_product(leaf, "d1", {"chuck": "sds"})
    make_product(leaf, "d2", {"chuck": "sds"})

    report = audit_sidebars([leaf])[0]

    # Единственный вариант ничего не сужает: нажать на него — получить ту же выдачу.
    assert report.usable_facets == []
    assert report.empty_facets == ["chuck"]


def test_два_значения_дают_рабочий_фасет(tree):
    root, leaf, _ = tree
    make_product(leaf, "d1", {"chuck": "sds"})
    make_product(leaf, "d2", {"chuck": "bzp"})

    report = audit_sidebars([leaf])[0]

    assert report.usable_facets == ["chuck"]
    assert report.has_sidebar


def test_заполненная_но_непривязанная_ось_попадает_в_чинибельные(tree):
    root, leaf, attr = tree
    free = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER, is_filterable=True
    )
    CategoryAttribute.objects.create(category=root, attribute=free)  # чтобы атрибут был известен
    CategoryAttribute.objects.filter(attribute=free).delete()
    for i in range(4):
        make_product(leaf, f"d{i}", {"power": 500 + i * 100})

    report = audit_sidebars([leaf], min_axis_products=2)[0]

    # Данные есть, фасета нет — единственный случай, который чинится привязкой,
    # а не наполнением. Именно его отчёт и должен выделять.
    assert [slug for slug, _v, _n in report.unbound_axes] == ["power"]


def test_привязка_на_невидимой_категории_считается_мёртвой(tree):
    root, leaf, attr = tree
    dead_root = Category.add_root(name="Легаси", slug="legacy", on_site=False)
    orphan = Attribute.objects.create(
        slug="bore", name="Посадка", attribute_type=AttributeType.TEXT, is_filterable=True
    )
    CategoryAttribute.objects.create(category=dead_root, attribute=orphan)

    report = audit_bindings(visible_categories())

    assert [ca.attribute.slug for ca in report.dead] == ["bore"]
    # Атрибута нет ни на одной живой категории — фасет потерян целиком, а не
    # продублирован. Это и есть случай «фасет висит на мёртвом двойнике».
    assert report.dead_only == ["bore"]
    assert report.depth_histogram == {1: 1}


def test_атрибут_без_привязок_виден_как_сирота(tree):
    Attribute.objects.create(
        slug="jack_type", name="Тип", attribute_type=AttributeType.TEXT, is_filterable=False
    )

    report = audit_bindings(visible_categories())

    assert [a.slug for a in report.orphan_attributes] == ["jack_type"]


def test_круг_фасет_фильтр_сходится(tree):
    root, leaf, _ = tree
    make_product(leaf, "d1", {"chuck": "sds"})
    make_product(leaf, "d2", {"chuck": "sds"})
    make_product(leaf, "d3", {"chuck": "bzp"})

    result = check_circle(visible_categories())

    assert result.drift == []
    assert result.pairs > 0


def test_расхождение_счётчиков_роняет_команду(tree, monkeypatch):
    root, leaf, _ = tree
    make_product(leaf, "d1", {"chuck": "sds"})
    make_product(leaf, "d2", {"chuck": "bzp"})

    # Подменяем фильтр так, будто он теряет товары: счётчик фасета говорит одно,
    # выдача показывает другое. Замер, который на этом промолчит, не нужен.
    from apps.catalog import facet_audit

    monkeypatch.setattr(facet_audit, "apply_product_attr_filters", lambda qs, *a, **kw: qs.none())

    with pytest.raises(CommandError):
        call_command("catalog_facet_audit", "--circle", stdout=open("/dev/null", "w"))


def test_отчёт_пишется_в_файл(tree, tmp_path):
    root, leaf, _ = tree
    make_product(leaf, "d1", {"chuck": "sds"})
    make_product(leaf, "d2", {"chuck": "bzp"})
    path = tmp_path / "report.md"

    call_command("catalog_facet_audit", markdown=str(path), stdout=open("/dev/null", "w"))

    text = path.read_text(encoding="utf-8")
    assert "# Аудит фильтров каталога" in text
    assert "Круг «фасет → фильтр»" in text
