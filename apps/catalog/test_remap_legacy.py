"""Тесты catalog_remap_legacy — структурный перенос курированного легаси → v2 по имени.

Совпадение имён (с нормализацией ё/регистр/пробелы) → товары переезжают в одноимённый
v2-узел с manual=True; несопоставленные легаси-узлы остаются на месте; dry-run ничего
не пишет; откат восстанавливает. Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import Category, Product, ProductStatus


def _p(name, slug, cat, *, manual=True):
    return Product.objects.create(
        name=name, slug=slug, category=cat, category_is_manual=manual, status=ProductStatus.IMPORTED
    )


@pytest.fixture
def trees(db):
    # v2-скелет раздела (slug из SECTION_RULES — берём krepezh).
    v2 = Category.add_root(name="Крепёж и метизы", slug="krepezh", is_site_v2=True)
    v2 = Category.objects.get(pk=v2.pk)
    v2_bolty = v2.add_child(name="Болты", slug="krepezh-bolty", is_site_v2=True)
    v2_zakl = v2.add_child(name="Заклёпки", slug="krepezh-zaklepki", is_site_v2=True)

    # Легаси-дерево (вручную разложенное).
    leg = Category.add_root(name="Крепёж легаси", slug="krepezh-i-metizy")
    leg = Category.objects.get(pk=leg.pk)
    leg_bolty = leg.add_child(name="Болты", slug="bolty")
    leg_zakl = leg.add_child(name="Заклепки", slug="zaklepki")  # без ё — проверка нормализации
    leg_kanat = leg.add_child(name="Крепёж, канат, верёвка", slug="kanat")  # нет v2-пары

    _p("Болт М8", "b1", leg_bolty)
    _p("Болт М10", "b2", leg_bolty)
    _p("Заклёпка 4мм", "z1", leg_zakl)
    _p("Канат 6мм", "k1", leg_kanat, manual=False)
    return {
        "v2_bolty": v2_bolty,
        "v2_zakl": v2_zakl,
        "leg_kanat": leg_kanat,
    }


@pytest.mark.django_db
def test_dry_run_moves_nothing(trees):
    out = StringIO()
    call_command(
        "catalog_remap_legacy", "--section", "krepezh", "--from", "krepezh-i-metizy", stdout=out
    )
    assert "DRY-RUN" in out.getvalue()
    # Ничего не переехало.
    assert Product.objects.get(slug="b1").category.slug == "bolty"


@pytest.mark.django_db
def test_commit_moves_by_name_preserving_manual(trees):
    call_command(
        "catalog_remap_legacy",
        "--section",
        "krepezh",
        "--from",
        "krepezh-i-metizy",
        "--commit",
        stdout=StringIO(),
    )
    # «Болты» → v2 «Болты», manual сохранён.
    b1 = Product.objects.get(slug="b1")
    assert b1.category_id == trees["v2_bolty"].id
    assert b1.category_is_manual is True
    # «Заклепки» (без ё) сопоставились с v2 «Заклёпки» по нормализации.
    z1 = Product.objects.get(slug="z1")
    assert z1.category_id == trees["v2_zakl"].id
    # Несопоставленный «канат» остался в легаси.
    k1 = Product.objects.get(slug="k1")
    assert k1.category_id == trees["leg_kanat"].id


@pytest.mark.django_db
def test_explicit_map_moves_diverging_name(trees):
    # Легаси «Крепёж, канат, верёвка» названо иначе, чем v2; через --map уводим в «Болты».
    call_command(
        "catalog_remap_legacy",
        "--section",
        "krepezh",
        "--from",
        "krepezh-i-metizy",
        "--map",
        "Крепёж, канат, верёвка=Болты",
        "--commit",
        stdout=StringIO(),
    )
    k1 = Product.objects.get(slug="k1")
    assert k1.category_id == trees["v2_bolty"].id
    assert k1.category_is_manual is True


@pytest.mark.django_db
def test_map_to_unknown_v2_node_errors(trees):
    with pytest.raises(CommandError):
        call_command(
            "catalog_remap_legacy",
            "--section",
            "krepezh",
            "--from",
            "krepezh-i-metizy",
            "--map",
            "Канат=НесуществующийУзел",
            stdout=StringIO(),
        )


@pytest.mark.django_db
def test_map_without_equals_errors(trees):
    with pytest.raises(CommandError):
        call_command(
            "catalog_remap_legacy",
            "--section",
            "krepezh",
            "--from",
            "krepezh-i-metizy",
            "--map",
            "безравно",
            stdout=StringIO(),
        )


@pytest.mark.django_db
def test_unmatched_product_gets_manual_on_match_only(trees):
    # Товар в сопоставленном узле, который был manual=False, после переноса становится manual=True.
    leg_bolty = Category.objects.get(slug="bolty")
    _p("Болт нерж", "b3", leg_bolty, manual=False)
    call_command(
        "catalog_remap_legacy",
        "--section",
        "krepezh",
        "--from",
        "krepezh-i-metizy",
        "--commit",
        stdout=StringIO(),
    )
    b3 = Product.objects.get(slug="b3")
    assert b3.category_id == trees["v2_bolty"].id
    assert b3.category_is_manual is True


@pytest.mark.django_db
def test_rollback_restores(trees, tmp_path, settings, monkeypatch):
    import apps.catalog.management.commands.catalog_remap_legacy as mod

    monkeypatch.setattr(mod.settings, "BASE_DIR", tmp_path)
    call_command(
        "catalog_remap_legacy",
        "--section",
        "krepezh",
        "--from",
        "krepezh-i-metizy",
        "--commit",
        stdout=StringIO(),
    )
    snap = next((tmp_path / "var" / "restructure").glob("remap-krepezh-*.json"))

    call_command("catalog_remap_legacy", "--rollback", str(snap), stdout=StringIO())
    # Болт вернулся в легаси.
    assert Product.objects.get(slug="b1").category.slug == "bolty"


@pytest.mark.django_db
def test_requires_existing_v2_root(db):
    Category.add_root(name="Легаси", slug="krepezh-i-metizy")
    with pytest.raises(CommandError):
        call_command(
            "catalog_remap_legacy",
            "--section",
            "krepezh",
            "--from",
            "krepezh-i-metizy",
            stdout=StringIO(),
        )
