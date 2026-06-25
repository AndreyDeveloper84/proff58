"""Тесты команды catalog_v2_swap (вариант A — секционный swap v2↔legacy).

Проверяет:
  * после build (скрыто) swap делает v2-узлы видимыми, КРОМЕ «На модерацию»;
  * указанный legacy-корень скрывается (is_active=False, on_site=False);
  * dry-run ничего не меняет; guard требует --force при непустом legacy;
  * --rollback восстанавливает видимость.

Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, Product, ProductStatus


def _mk(name, slug, **kw):
    return Product.objects.create(name=name, slug=slug, status=ProductStatus.IMPORTED, **kw)


@pytest.fixture
def built():
    """Скрытый v2 osnastka + legacy-корень с товаром."""
    _mk("Сверло по металлу 5 мм HSS", "p-sverlo")
    _mk("Пилка универсальная", "p-pilka")  # → модерация
    legacy = Category.add_root(name="Оснастка и расходники", slug="osnastka-i-rashodniki")
    _mk("Прочий товар", "p-legacy", category=legacy)
    call_command("catalog_build_section", "--section", "osnastka", "--commit", stdout=StringIO())
    return legacy


@pytest.mark.django_db
def test_dry_run_changes_no_visibility(built):
    root = Category.objects.get(slug="osnastka")
    call_command(
        "catalog_v2_swap",
        "--section",
        "osnastka",
        "--hide-legacy",
        "osnastka-i-rashodniki",
        stdout=StringIO(),
    )
    root.refresh_from_db()
    assert root.is_active is False and root.on_site is False  # dry-run не тронул


@pytest.mark.django_db
def test_guard_blocks_nonempty_legacy_without_force(built):
    with pytest.raises(CommandError):
        call_command(
            "catalog_v2_swap",
            "--section",
            "osnastka",
            "--hide-legacy",
            "osnastka-i-rashodniki",
            "--commit",
            stdout=StringIO(),
        )


@pytest.mark.django_db
def test_commit_swaps_visibility(built):
    call_command(
        "catalog_v2_swap",
        "--section",
        "osnastka",
        "--hide-legacy",
        "osnastka-i-rashodniki",
        "--commit",
        "--force",
        stdout=StringIO(),
    )
    root = Category.objects.get(slug="osnastka")
    sverla = Category.objects.get(name="Свёрла")
    moderation = Category.objects.get(name="На модерацию")
    legacy = Category.objects.get(slug="osnastka-i-rashodniki")

    assert root.is_active and root.on_site  # v2 показан
    assert sverla.is_active and sverla.on_site
    assert moderation.is_active is False and moderation.on_site is False  # модерация скрыта
    assert legacy.is_active is False and legacy.on_site is False  # legacy скрыт

    swaps = sorted((Path(settings.BASE_DIR) / "var" / "restructure").glob("swap-osnastka-*.json"))
    assert swaps, "снимок swap не создан"


@pytest.mark.django_db
def test_rollback_restores_visibility(built):
    call_command(
        "catalog_v2_swap",
        "--section",
        "osnastka",
        "--hide-legacy",
        "osnastka-i-rashodniki",
        "--commit",
        "--force",
        stdout=StringIO(),
    )
    snap = sorted((Path(settings.BASE_DIR) / "var" / "restructure").glob("swap-osnastka-*.json"))[
        -1
    ]
    call_command("catalog_v2_swap", "--rollback", str(snap), stdout=StringIO())

    root = Category.objects.get(slug="osnastka")
    legacy = Category.objects.get(slug="osnastka-i-rashodniki")
    assert root.is_active is False and root.on_site is False  # вернулось к скрытому
    assert legacy.is_active and legacy.on_site  # legacy снова видим
