"""Тесты catalog_seed_filters — посев CategoryAttribute с легаси-корня на v2-корень.

Проверяет: dry-run ничего не создаёт; --commit копирует строки на v2-корень
(сохраняя is_filter/group/sort_order), идемпотентность; --rollback удаляет.

Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.catalog.models import Attribute, Category, CategoryAttribute


@pytest.fixture
def setup():
    legacy = Category.add_root(name="Оснастка legacy", slug="osnastka-legacy", on_site=True)
    v2 = Category.add_root(name="Оснастка и расходные материалы", slug="osnastka", on_site=False)
    a1 = Attribute.objects.create(slug="diametr", name="Диаметр", is_filterable=True)
    a2 = Attribute.objects.create(slug="material", name="Материал", is_filterable=True)
    CategoryAttribute.objects.create(category=legacy, attribute=a1, is_filter=True, sort_order=1)
    CategoryAttribute.objects.create(category=legacy, attribute=a2, is_filter=False, sort_order=2)
    return {"legacy": legacy, "v2": v2, "a1": a1, "a2": a2}


@pytest.mark.django_db
def test_dry_run_creates_nothing(setup):
    out = StringIO()
    call_command(
        "catalog_seed_filters", "--section", "osnastka", "--from", "osnastka-legacy", stdout=out
    )
    assert "DRY-RUN" in out.getvalue()
    assert setup["v2"].category_attributes.count() == 0


@pytest.mark.django_db
def test_commit_copies_rows(setup):
    call_command(
        "catalog_seed_filters",
        "--section",
        "osnastka",
        "--from",
        "osnastka-legacy",
        "--commit",
        stdout=StringIO(),
    )
    v2 = setup["v2"]
    assert v2.category_attributes.count() == 2  # обе строки скопированы
    diam = v2.category_attributes.get(attribute=setup["a1"])
    assert diam.is_filter is True and diam.sort_order == 1
    mat = v2.category_attributes.get(attribute=setup["a2"])
    assert mat.is_filter is False  # метаданные сохранены

    backups = sorted(
        (Path(settings.BASE_DIR) / "var" / "restructure").glob("seedfilters-osnastka-*.json")
    )
    assert backups


@pytest.mark.django_db
def test_idempotent(setup):
    for _ in range(2):
        call_command(
            "catalog_seed_filters",
            "--section",
            "osnastka",
            "--from",
            "osnastka-legacy",
            "--commit",
            stdout=StringIO(),
        )
    assert setup["v2"].category_attributes.count() == 2  # не задублировалось


@pytest.mark.django_db
def test_rollback(setup):
    call_command(
        "catalog_seed_filters",
        "--section",
        "osnastka",
        "--from",
        "osnastka-legacy",
        "--commit",
        stdout=StringIO(),
    )
    snap = sorted(
        (Path(settings.BASE_DIR) / "var" / "restructure").glob("seedfilters-osnastka-*.json")
    )[-1]
    call_command("catalog_seed_filters", "--rollback", str(snap), stdout=StringIO())
    assert setup["v2"].category_attributes.count() == 0


@pytest.mark.django_db
def test_missing_source_errors(setup):
    with pytest.raises(CommandError):
        call_command(
            "catalog_seed_filters",
            "--section",
            "osnastka",
            "--from",
            "nesuschestvuet",
            "--commit",
            stdout=StringIO(),
        )
