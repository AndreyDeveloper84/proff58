"""Тесты применения сопоставления «группа 1С → категория» (Фаза 2).

Проверяет apply_group_mapping (перенос товаров группы в mapped_category, manual=True,
пропуск ручных и чужих групп) и команду catalog_apply_group_mapping. Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, OneCGroup, OneCGroupStatus, Product, ProductStatus
from apps.catalog.onec_groups import apply_group_mapping


def _p(name, slug, group, **kw):
    return Product.objects.create(
        name=name, slug=slug, source_group=group, status=ProductStatus.IMPORTED, **kw
    )


@pytest.mark.django_db
def test_apply_moves_group_products():
    cat = Category.add_root(name="Биты v2", slug="bity-v2")
    other = Category.add_root(name="Чужая", slug="chuzhaya")
    g = OneCGroup.objects.create(name="Биты", mapped_category=cat, status=OneCGroupStatus.ACTIVE)

    p1 = _p("Бита 1", "p1", "Биты")  # переедет
    p2 = _p(
        "Бита ручная", "p2", "Биты", category=other, category_is_manual=True
    )  # ручная — не трогаем
    p3 = _p("Свёрло", "p3", "Свёрла")  # другая группа — не трогаем

    moved = apply_group_mapping(g)
    assert moved == 1

    p1.refresh_from_db()
    p2.refresh_from_db()
    p3.refresh_from_db()
    assert p1.category_id == cat.id and p1.category_is_manual is True
    assert p2.category_id == other.id  # ручная сохранена
    assert p3.category_id is None  # чужая группа не тронута


@pytest.mark.django_db
def test_no_category_returns_zero():
    g = OneCGroup.objects.create(name="Безкатегории", mapped_category=None)
    _p("Товар", "p1", "Безкатегории")
    assert apply_group_mapping(g) == 0


@pytest.mark.django_db
def test_command_requires_target():
    with pytest.raises(CommandError):
        call_command("catalog_apply_group_mapping", stdout=StringIO())


@pytest.mark.django_db
def test_command_all_commit():
    cat = Category.add_root(name="Биты v2", slug="bity-v2")
    OneCGroup.objects.create(name="Биты", mapped_category=cat, status=OneCGroupStatus.ACTIVE)
    p = _p("Бита", "p1", "Биты")

    # dry-run не трогает
    call_command("catalog_apply_group_mapping", "--all", stdout=StringIO())
    p.refresh_from_db()
    assert p.category_id is None

    call_command("catalog_apply_group_mapping", "--all", "--commit", stdout=StringIO())
    p.refresh_from_db()
    assert p.category_id == cat.id and p.category_is_manual is True
