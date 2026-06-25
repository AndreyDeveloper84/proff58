"""Тесты команды catalog_build_section (E3 — построение раздела + расселение).

Вариант A («скрыто → секционный swap»). Использует реальный словарь
data/product_type_rules.json. Проверяет:
  * dry-run ничего не создаёт и не перемещает;
  * --commit создаёт узлы СКРЫТЫМИ (is_active=False, on_site=False), high-confidence
    → нормальный узел (category_is_manual=True), medium/low → скрытый узел
    «На модерацию» (category_is_manual=False), уже-ручные не трогает;
  * --rollback восстанавливает товары и удаляет созданные пустые узлы.

Нужен PostgreSQL (как и остальной каталог).
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.catalog.models import Category, Product, ProductStatus


def _mk(name, slug, **kw):
    return Product.objects.create(name=name, slug=slug, status=ProductStatus.IMPORTED, **kw)


@pytest.fixture
def products():
    return {
        "sverlo": _mk("Сверло по металлу 5 мм HSS", "p-sverlo"),  # → Свёрла (high)
        "krug": _mk("Круг лепестковый КЛТ 125 P40", "p-krug"),  # → Круги/Лепестковые (high)
        "pilka": _mk("Пилка универсальная", "p-pilka"),  # → Пильная оснастка (medium) → модерация
        "bolt": _mk("Болт М10х50 DIN933", "p-bolt"),  # не Оснастка → не трогаем
        "molotok": _mk("Молоток слесарный 500 г", "p-molotok"),  # Ручной → не трогаем здесь
    }


@pytest.mark.django_db
def test_dry_run_changes_nothing(products):
    out = StringIO()
    call_command("catalog_build_section", "--section", "osnastka", stdout=out)
    assert "DRY-RUN" in out.getvalue()
    assert not Category.objects.filter(slug="osnastka").exists()
    for p in products.values():
        p.refresh_from_db()
        assert p.category_id is None


@pytest.mark.django_db
def test_commit_builds_hidden_tree_and_assigns(products):
    out = StringIO()
    call_command("catalog_build_section", "--section", "osnastka", "--commit", stdout=out)
    assert "COMMIT" in out.getvalue()

    root = Category.objects.get(slug="osnastka")
    sverla = Category.objects.get(name="Свёрла")
    krugi = Category.objects.get(name="Круги")
    lepest = Category.objects.get(name="Лепестковые")
    assert sverla.get_parent().pk == root.pk
    assert lepest.get_parent().pk == krugi.pk  # 3-й уровень

    # Все новые узлы — скрытые (вариант A: видимость включает только swap).
    for node in (root, sverla, krugi, lepest):
        assert node.is_active is False
        assert node.on_site is False

    products["sverlo"].refresh_from_db()
    products["krug"].refresh_from_db()
    products["bolt"].refresh_from_db()
    assert products["sverlo"].category_id == sverla.pk
    assert products["sverlo"].category_is_manual is True
    assert products["krug"].category_id == lepest.pk  # ушёл в подтип
    assert products["bolt"].category_id is None  # не Оснастка — не тронут

    backups = sorted(
        (Path(settings.BASE_DIR) / "var" / "restructure").glob("build-osnastka-*.json")
    )
    assert backups, "снимок отката не создан"


@pytest.mark.django_db
def test_commit_medium_goes_to_moderation(products):
    call_command("catalog_build_section", "--section", "osnastka", "--commit", stdout=StringIO())

    moderation = Category.objects.get(name="На модерацию")
    assert moderation.is_active is False and moderation.on_site is False

    products["pilka"].refresh_from_db()
    assert products["pilka"].category_id == moderation.pk
    assert products["pilka"].category_is_manual is False  # ждёт ручного разбора

    # CSV модерации создан и содержит товар.
    csvs = sorted(
        (Path(settings.BASE_DIR) / "var" / "restructure").glob("moderation-osnastka-*.csv")
    )
    assert csvs, "CSV модерации не создан"
    body = csvs[-1].read_text(encoding="utf-8")
    assert "Пилка универсальная" in body
    assert "low_confidence" in body


@pytest.mark.django_db
def test_commit_skips_manual(products):
    # Уже-ручной товар, который классифицируется как оснастка, НЕ перетирается.
    sverlo = products["sverlo"]
    other = Category.add_root(name="Чужая", slug="chuzhaya")
    sverlo.category = other
    sverlo.category_is_manual = True
    sverlo.save(update_fields=["category", "category_is_manual"])

    call_command("catalog_build_section", "--section", "osnastka", "--commit", stdout=StringIO())

    sverlo.refresh_from_db()
    assert sverlo.category_id == other.pk  # ручная категория сохранена


@pytest.mark.django_db
def test_rollback_restores(products):
    call_command("catalog_build_section", "--section", "osnastka", "--commit", stdout=StringIO())
    snap = sorted((Path(settings.BASE_DIR) / "var" / "restructure").glob("build-osnastka-*.json"))[
        -1
    ]

    call_command("catalog_build_section", "--rollback", str(snap), stdout=StringIO())

    products["sverlo"].refresh_from_db()
    products["pilka"].refresh_from_db()
    assert products["sverlo"].category_id is None
    assert products["sverlo"].category_is_manual is False
    assert products["pilka"].category_id is None  # из модерации тоже откатился
    # Созданные пустые узлы удалены.
    assert not Category.objects.filter(slug="osnastka").exists()
    assert not Category.objects.filter(name="На модерацию").exists()
