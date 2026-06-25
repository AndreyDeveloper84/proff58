"""Тесты catalog_build_skeleton — полный скелет v2-дерева видимым, без товаров.

Проверяет: dry-run ничего не создаёт; --commit создаёт узлы ВИДИМЫМИ и НЕ двигает
товары; идемпотентность; --hidden создаёт скрыто; --rollback удаляет пустые.

Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.catalog.models import Category, Product, ProductStatus


@pytest.mark.django_db
def test_dry_run_creates_nothing():
    out = StringIO()
    call_command("catalog_build_skeleton", "--section", "osnastka", stdout=out)
    assert "DRY-RUN" in out.getvalue()
    assert not Category.objects.filter(slug="osnastka").exists()


@pytest.mark.django_db
def test_commit_builds_visible_tree_no_products():
    p = Product.objects.create(
        name="Сверло по металлу 5 мм", slug="p-sv", status=ProductStatus.IMPORTED
    )
    call_command("catalog_build_skeleton", "--section", "osnastka", "--commit", stdout=StringIO())

    root = Category.objects.get(slug="osnastka")
    sverla = Category.objects.get(name="Свёрла")
    assert root.is_active and root.on_site  # видимо на фронте
    assert sverla.is_active and sverla.on_site
    assert sverla.get_parent().pk == root.pk

    p.refresh_from_db()
    assert p.category_id is None  # товары НЕ тронуты (чистая структура)

    backups = sorted((Path(settings.BASE_DIR) / "var" / "restructure").glob("skeleton-*.json"))
    assert backups


@pytest.mark.django_db
def test_hidden_flag_creates_hidden():
    call_command(
        "catalog_build_skeleton", "--section", "osnastka", "--hidden", "--commit", stdout=StringIO()
    )
    root = Category.objects.get(slug="osnastka")
    assert root.is_active is False and root.on_site is False


@pytest.mark.django_db
def test_idempotent_and_sets_visibility():
    # первый прогон скрыто, второй — видимо: узлы переиспользуются, видимость меняется.
    call_command(
        "catalog_build_skeleton", "--section", "osnastka", "--hidden", "--commit", stdout=StringIO()
    )
    n1 = Category.objects.count()
    call_command("catalog_build_skeleton", "--section", "osnastka", "--commit", stdout=StringIO())
    assert Category.objects.count() == n1  # дублей не создано
    assert Category.objects.get(slug="osnastka").on_site is True  # стало видимо


@pytest.mark.django_db
def test_rollback_removes_empty():
    call_command("catalog_build_skeleton", "--section", "osnastka", "--commit", stdout=StringIO())
    snap = sorted((Path(settings.BASE_DIR) / "var" / "restructure").glob("skeleton-*.json"))[-1]
    call_command("catalog_build_skeleton", "--rollback", str(snap), stdout=StringIO())
    assert not Category.objects.filter(slug="osnastka").exists()
