"""Упаковка для доставки СДЭК (DRF-2299): наследование по дереву разделов."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.catalog.models import Category, Product, ProductStatus
from apps.catalog.packaging import Package, package_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def дерево():
    root = Category.add_root(
        name="Электроинструмент",
        slug="pk-root",
        package_weight_g=3000,
        package_length_cm=40,
        package_width_cm=30,
        package_height_cm=15,
    )
    child = root.add_child(name="Перфораторы", slug="pk-child", package_weight_g=5000)
    leaf = child.add_child(name="SDS-max", slug="pk-leaf")
    bare = Category.add_root(name="Крепёж", slug="pk-bare")
    return root, child, leaf, bare


def _product(category, slug, **kw):
    return Product.objects.create(
        name=slug,
        slug=slug,
        price=Decimal("100"),
        category=category,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        **kw,
    )


def test_товар_берёт_упаковку_у_ближайшего_раздела_раздельно_вес_и_габариты(дерево):
    root, child, leaf, _ = дерево
    p = _product(leaf, "pk-1")
    # вес — у «Перфораторов» (ближе), габариты — только у корня
    assert package_for([p.pk])[p.pk] == Package(5000, 40, 30, 15)


def test_товар_может_уточнить_только_вес(дерево):
    _, _, leaf, _ = дерево
    p = _product(leaf, "pk-2", package_weight_g=7200)
    assert package_for([p.pk])[p.pk] == Package(7200, 40, 30, 15)


def test_свои_габариты_товара_важнее_раздела(дерево):
    _, _, leaf, _ = дерево
    p = _product(leaf, "pk-3", package_length_cm=60, package_width_cm=20, package_height_cm=20)
    assert package_for([p.pk])[p.pk] == Package(5000, 60, 20, 20)


def test_нет_упаковки_нигде_значит_none(дерево):
    *_, bare = дерево
    p = _product(bare, "pk-4")
    q = _product(None, "pk-5")
    result = package_for([p.pk, q.pk])
    assert result[p.pk] is None and result[q.pk] is None


def test_вес_без_габаритов_не_упаковка(дерево):
    *_, bare = дерево
    p = _product(bare, "pk-6", package_weight_g=500)
    assert package_for([p.pk])[p.pk] is None


def test_неполная_тройка_габаритов_не_сохраняется(дерево):
    *_, bare = дерево
    bare.package_length_cm = 10
    with pytest.raises(ValidationError):
        bare.full_clean()


def test_запросов_не_больше_двух_на_любое_число_товаров(дерево, django_assert_max_num_queries):
    _, _, leaf, bare = дерево
    ids = [_product(leaf if i % 2 else bare, f"pk-n{i}").pk for i in range(20)]
    with django_assert_max_num_queries(2):
        package_for(ids)


def test_отчёт_показывает_покрытие_по_разделам(дерево):
    _, _, leaf, bare = дерево
    _product(leaf, "pk-r1")
    _product(bare, "pk-r2")
    out = StringIO()
    call_command("catalog_packaging_report", stdout=out)
    text = out.getvalue()
    assert "с упаковкой: 1" in text
    assert "Электроинструмент" in text and "1/1" in text
    assert "Крепёж" in text and "0/1" in text and "не задано" in text
    out = StringIO()
    call_command("catalog_packaging_report", "--missing", stdout=out)
    assert "Электроинструмент" not in out.getvalue() and "Крепёж" in out.getvalue()


def test_импорт_1с_не_трогает_упаковку():
    from apps.sync_1c.bulk_import import _PRODUCT_UPDATE_FIELDS

    assert not [f for f in _PRODUCT_UPDATE_FIELDS if f.startswith("package_")]
