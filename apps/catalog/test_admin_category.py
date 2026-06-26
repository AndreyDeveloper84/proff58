"""Тесты колонок-счётчиков товаров в админке категорий.

«Товаров»/«Опубл.» считаются по ВСЕМУ поддереву (узел + потомки) — у родительских
узлов, чьи товары лежат в листьях, число не нулевое. Счётчик — ссылка-drill-down в
список товаров, отфильтрованный по поддереву (``category__path__startswith=<path>``),
поэтому число и открытая страница совпадают.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.catalog.admin import CategoryAdmin
from apps.catalog.models import Category, Product, ProductStatus

User = get_user_model()


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_superuser(phone="+79990000088", password="pw")
    c = Client()
    c.force_login(admin)
    return c


def _leaf_with_product():
    root = Category.add_root(name="Электроинструмент", slug="ei")
    root = Category.objects.get(pk=root.pk)
    leaf = root.add_child(name="Дрели", slug="dreli")
    Product.objects.create(
        name="Дрель", slug="d1", category=leaf, status=ProductStatus.PUBLISHED, is_active=True
    )
    return leaf


@pytest.mark.django_db
def test_category_count_links_to_subtree_products(admin_client):
    """В списке категорий счётчик «Товаров» — ссылка на список товаров поддерева."""
    leaf = _leaf_with_product()

    resp = admin_client.get(reverse("admin:catalog_category_changelist"))
    assert resp.status_code == 200
    target = f'{reverse("admin:catalog_product_changelist")}?category__path__startswith={leaf.path}'
    assert target in resp.content.decode()


@pytest.mark.django_db
def test_product_changelist_accepts_subtree_lookup(admin_client):
    """Ссылка-drill-down открывается: lookup category__path__startswith разрешён (иначе
    DisallowedModelAdminLookup), товар поддерева в выдаче."""
    leaf = _leaf_with_product()

    url = f'{reverse("admin:catalog_product_changelist")}?category__path__startswith={leaf.path}'
    resp = admin_client.get(url)
    assert resp.status_code == 200
    assert "Дрель" in resp.content.decode()


@pytest.mark.django_db
def test_category_change_page_shows_product_count(admin_client):
    """На странице правки категории есть поле «Товаров в категории» со ссылкой-drill-down."""
    leaf = _leaf_with_product()

    resp = admin_client.get(reverse("admin:catalog_category_change", args=[leaf.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Товаров в категории" in html
    target = f'{reverse("admin:catalog_product_changelist")}?category__path__startswith={leaf.path}'
    assert target in html


@pytest.mark.django_db
def test_subtree_rollup_counts_descendants():
    """Родитель показывает товары всего поддерева; «Опубл.» — только опубликованные.

    Дерево: Оснастка → Свёрла → {Свёрла по металлу, Свёрла по дереву}. Товары лежат в
    листьях, у корня прямых товаров нет — но _products/_published накапливают поддерево.
    """
    root = Category.add_root(name="Оснастка", slug="osn")
    root = Category.objects.get(pk=root.pk)
    sverla = root.add_child(name="Свёрла", slug="osn-sverla")
    sverla = Category.objects.get(pk=sverla.pk)
    metal = sverla.add_child(name="По металлу", slug="osn-sverla-metal")
    wood = sverla.add_child(name="По дереву", slug="osn-sverla-wood")

    Product.objects.create(
        name="Сверло М1", slug="m1", category=metal, status=ProductStatus.PUBLISHED
    )
    Product.objects.create(
        name="Сверло М2", slug="m2", category=metal, status=ProductStatus.IMPORTED
    )
    Product.objects.create(
        name="Сверло Д1", slug="dd1", category=wood, status=ProductStatus.PUBLISHED
    )

    admin = CategoryAdmin(Category, AdminSite())
    request = RequestFactory().get("/admin/catalog/category/")
    qs = admin.get_queryset(request)
    by_id = {c.id: c for c in qs}

    # Корень: 3 товара всего, 2 опубликованных — из обоих листьев.
    assert by_id[root.id]._products == 3
    assert by_id[root.id]._published == 2
    # Промежуточный узел «Свёрла» — тоже накрывает оба листа.
    assert by_id[sverla.id]._products == 3
    assert by_id[sverla.id]._published == 2
    # Лист «По металлу» — свои 2 (1 опубл.).
    assert by_id[metal.id]._products == 2
    assert by_id[metal.id]._published == 1
    # Лист «По дереву» — свой 1 (1 опубл.).
    assert by_id[wood.id]._products == 1
    assert by_id[wood.id]._published == 1
