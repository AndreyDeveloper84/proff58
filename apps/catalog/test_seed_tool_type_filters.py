"""Тест catalog_seed_tool_type_filters — инвариант «узел-тип несёт свои фасеты».

Перенесённый в use-раздел узел-тип («Домкраты» под «Автоинструмент») теряет
наследование фильтров от корня-источника. Команда ставит атрибуты преобладающего
tool_type ЛОКАЛЬНО на узел → _category_filter_attributes снова их видит. Нужен PostgreSQL.
Использует реальный data/attribute_rules.json (domkraty → capacity, domkrat_type).
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
)
from apps.catalog.queries import _category_filter_attributes


def _tool_type_attr():
    attr, _ = Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )
    return attr


@pytest.fixture
def domkraty_node(db):
    # Атрибуты-фильтры типа (как создаёт load_attributes из attribute_rules).
    for slug, name in [("capacity", "Грузоподъёмность"), ("domkrat_type", "Тип домкрата")]:
        Attribute.objects.get_or_create(slug=slug, defaults={"name": name, "is_filterable": True})
    tt = _tool_type_attr()
    opt, _ = AttributeOption.objects.get_or_create(
        attribute=tt, value="Домкраты", defaults={"slug": "domkraty"}
    )

    # Узел-тип переехал в use-раздел (предок — НЕ «Ручной инструмент»).
    avto = Category.add_root(name="Автоинструмент и гаражное оборудование", slug="avto-x")
    avto = Category.objects.get(pk=avto.pk)
    dom = avto.add_child(name="Домкраты", slug="domkraty", is_site_v2=True)

    for i in range(8):
        p = Product.objects.create(
            name=f"Домкрат {i}", slug=f"dk-{i}", category=dom, status=ProductStatus.PUBLISHED
        )
        ProductAttributeValue.objects.create(product=p, attribute=tt, value_option=opt)
    return dom


@pytest.mark.django_db
def test_dry_run_writes_nothing(domkraty_node):
    out = StringIO()
    call_command("catalog_seed_tool_type_filters", stdout=out)
    assert "DRY-RUN" in out.getvalue()
    assert CategoryAttribute.objects.filter(category=domkraty_node).count() == 0


@pytest.mark.django_db
def test_stamps_filters_locally_and_resolves(domkraty_node):
    call_command("catalog_seed_tool_type_filters", "--commit", stdout=StringIO())
    # Локальные CategoryAttribute появились на самом узле.
    local = set(
        CategoryAttribute.objects.filter(category=domkraty_node).values_list(
            "attribute__slug", flat=True
        )
    )
    assert {"capacity", "domkrat_type"} <= local
    # И резолв фильтров узла их видит, несмотря на чужого предка (move-proof).
    slugs = {a.slug for a in _category_filter_attributes(domkraty_node)}
    assert {"capacity", "domkrat_type"} <= slugs


@pytest.mark.django_db
def test_idempotent(domkraty_node):
    call_command("catalog_seed_tool_type_filters", "--commit", stdout=StringIO())
    n1 = CategoryAttribute.objects.filter(category=domkraty_node).count()
    call_command("catalog_seed_tool_type_filters", "--commit", stdout=StringIO())
    assert CategoryAttribute.objects.filter(category=domkraty_node).count() == n1


@pytest.mark.django_db
def test_broad_node_skipped(domkraty_node):
    # Широкий узел: два tool_type поровну → нет преобладания → не штампуем.
    tt = _tool_type_attr()
    other = AttributeOption.objects.create(attribute=tt, value="Вороток", slug="vorotki")
    broad = Category.add_root(name="Широкий", slug="broad-x", is_site_v2=True)
    broad = Category.objects.get(pk=broad.pk)
    opt_dom = AttributeOption.objects.get(attribute=tt, slug="domkraty")
    for i in range(4):
        for opt in (opt_dom, other):
            p = Product.objects.create(
                name=f"b{i}-{opt.slug}", slug=f"b{i}-{opt.slug}", category=broad
            )
            ProductAttributeValue.objects.create(product=p, attribute=tt, value_option=opt)
    call_command("catalog_seed_tool_type_filters", "--commit", stdout=StringIO())
    assert CategoryAttribute.objects.filter(category=broad).count() == 0
