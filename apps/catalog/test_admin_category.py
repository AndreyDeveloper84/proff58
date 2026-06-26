"""Тесты колонки-счётчика товаров в админке категорий: число — ссылка в список товаров,
отфильтрованный по этой категории (drill-down)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

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
    leaf = root.add_child(name="Дрели", slug="dreli")
    Product.objects.create(
        name="Дрель", slug="d1", category=leaf, status=ProductStatus.PUBLISHED, is_active=True
    )
    return leaf


@pytest.mark.django_db
def test_category_count_links_to_filtered_products(admin_client):
    """В списке категорий счётчик «Товаров» — ссылка на список товаров этой категории."""
    leaf = _leaf_with_product()

    resp = admin_client.get(reverse("admin:catalog_category_changelist"))
    assert resp.status_code == 200
    target = f'{reverse("admin:catalog_product_changelist")}?category__id__exact={leaf.pk}'
    assert target in resp.content.decode()


@pytest.mark.django_db
def test_product_changelist_accepts_category_lookup(admin_client):
    """Ссылка-drill-down открывается: lookup category__id__exact разрешён (иначе была бы
    DisallowedModelAdminLookup → ошибка), товар категории в выдаче."""
    leaf = _leaf_with_product()

    url = f'{reverse("admin:catalog_product_changelist")}?category__id__exact={leaf.pk}'
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
    target = f'{reverse("admin:catalog_product_changelist")}?category__id__exact={leaf.pk}'
    assert target in html
