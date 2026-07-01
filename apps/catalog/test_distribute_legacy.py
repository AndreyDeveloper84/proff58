"""Тесты команды catalog_distribute_legacy (распределение grab-bag legacy-узла).

Раздел «Хозтовары» (legacy id=35) в v2 не имеет 1:1-дома: его товары раскидываются
по существующим v2-разделам по значению ``tool_type`` (кластеры ``hoz-*``).

Перенос ОБЯЗАН быть scoped по узлу-источнику: товар с тем же ``hoz-*`` типом, но
лежащий ВНЕ поддерева источника, не трогается (``hoz-*`` типы не уникальны для
источника — те же есть в целевых разделах после прошлых раундов).

Нужен PostgreSQL (как и весь каталог).
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
)


@pytest.fixture
def bag():
    """Источник «Хозтовары» + 5 целевых разделов + товары под реальные slug'и.

    Соответствует DISTRIBUTIONS['hoztovary'] команды: источник и все таргеты
    должны существовать, иначе команда падает понятной ошибкой.
    """
    src = Category.add_root(name="Хозтовары, сад, огород", slug="hoztovary-sad-ogorod")
    sad = Category.add_root(name="Садовая техника и инвентарь", slug="sadovaya")
    krep = Category.add_root(name="Крепёж и метизы", slug="krepezh")
    ruch = Category.add_root(name="Ручной инструмент", slug="ruchnoy")
    stro = Category.add_root(name="Строительный и отделочный инструмент", slug="stroitelnyy")
    izm = Category.add_root(name="Измерительный инструмент", slug="izmeritelnyy")

    tt = Attribute.objects.create(slug="tool_type", name="Тип", attribute_type=AttributeType.SELECT)

    def opt(value, slug):
        return AttributeOption.objects.create(attribute=tt, value=value, slug=slug)

    o_lop = opt("Лопаты", "hoz-lopaty")  # → Садовая
    o_zam = opt("Замки", "hoz-zamki")  # → Крепёж
    o_lez = opt("Лезвия", "hoz-lezviya")  # → Ручной
    o_ple = opt("Плёнка", "hoz-plenka")  # → Строительный
    o_lup = opt("Лупы", "hoz-lupy")  # → Измерительный
    o_tru = opt("Трубы", "hoz-truby-fitingi")  # non-cluster (сантехника) → остаётся

    def mk(cat, slug, option=None):
        p = Product.objects.create(
            category=cat, name=slug, slug=slug, status=ProductStatus.PUBLISHED, is_active=True
        )
        if option is not None:
            ProductAttributeValue.objects.create(product=p, attribute=tt, value_option=option)
        return p

    products = {
        "sad": mk(src, "p-sad", o_lop),
        "krep": mk(src, "p-krep", o_zam),
        "ruch": mk(src, "p-ruch", o_lez),
        "plen": mk(src, "p-plen", o_ple),
        "lupa": mk(src, "p-lupa", o_lup),
        "santeh": mk(src, "p-santeh", o_tru),  # non-cluster → остаётся в источнике
        "fp": mk(src, "p-fp", o_ple),  # hoz-plenka, но исключим через --exclude-ids
        "foreign": mk(sad, "p-foreign", o_lop),  # ВНЕ источника → не трогать
    }
    return {
        "src": src,
        "targets": {
            "sadovaya": sad,
            "krepezh": krep,
            "ruchnoy": ruch,
            "stroitelnyy": stro,
            "izmeritelnyy": izm,
        },
        "p": products,
    }


@pytest.mark.django_db
def test_no_source_raises():
    """Без --source и без --rollback команда падает понятной ошибкой."""
    with pytest.raises(CommandError):
        call_command("catalog_distribute_legacy")


@pytest.mark.django_db
def test_missing_target_raises(bag):
    """Если целевой раздел отсутствует (нет slug и name) — команда падает."""
    bag["targets"]["krepezh"].delete()
    with pytest.raises(CommandError):
        call_command("catalog_distribute_legacy", "--source", "hoztovary")


@pytest.mark.django_db
def test_exclude_ids_drop_fp(bag):
    """--exclude-ids убирает конкретный товар из переноса (FP-исключение)."""
    out = StringIO()
    call_command(
        "catalog_distribute_legacy",
        "--source",
        "hoztovary",
        "--exclude-ids",
        str(bag["p"]["fp"].pk),
        stdout=out,
    )
    text = out.getvalue()

    # p-fp (hoz-plenka) исключён → Строительный move 1 (только p-plen), ИТОГО 5.
    assert "(stroitelnyy): move 1" in text
    assert "ИТОГО move: 5" in text
    assert "Исключено FP (по id): 1" in text


@pytest.mark.django_db
def test_commit_routes_and_manual(bag):
    """--commit: товары уходят в целевые разделы, category_is_manual=True,
    источник scoped (чужой не тронут), снимок отката создан."""
    from pathlib import Path

    out = StringIO()
    call_command(
        "catalog_distribute_legacy",
        "--source",
        "hoztovary",
        "--exclude-ids",
        str(bag["p"]["fp"].pk),
        "--commit",
        stdout=out,
    )
    text = out.getvalue()

    for p in bag["p"].values():
        p.refresh_from_db()
    t = bag["targets"]
    assert bag["p"]["sad"].category_id == t["sadovaya"].pk
    assert bag["p"]["krep"].category_id == t["krepezh"].pk
    assert bag["p"]["ruch"].category_id == t["ruchnoy"].pk
    assert bag["p"]["plen"].category_id == t["stroitelnyy"].pk
    assert bag["p"]["lupa"].category_id == t["izmeritelnyy"].pk
    assert all(
        bag["p"][k].category_is_manual is True for k in ("sad", "krep", "ruch", "plen", "lupa")
    )

    # non-cluster и FP остались в источнике; чужой (вне источника) не тронут.
    assert bag["p"]["santeh"].category_id == bag["src"].pk
    assert bag["p"]["fp"].category_id == bag["src"].pk
    assert bag["p"]["foreign"].category_id == t["sadovaya"].pk
    assert bag["p"]["foreign"].category_is_manual is False

    # Снимок отката создан.
    snap = text.split("Снимок отката:", 1)[1].strip().splitlines()[0].strip()
    assert Path(snap).exists()
    assert "hoztovary-" in snap


@pytest.mark.django_db
def test_second_commit_noop(bag):
    """Повторный --commit ничего не переносит (товары уже вне источника)."""
    args = (
        "catalog_distribute_legacy",
        "--source",
        "hoztovary",
        "--exclude-ids",
        str(bag["p"]["fp"].pk),
        "--commit",
    )
    call_command(*args, stdout=StringIO())
    out = StringIO()
    call_command(*args, stdout=out)
    assert "ИТОГО move: 0" in out.getvalue()


@pytest.mark.django_db
def test_rollback_restores(bag):
    """--rollback возвращает товары в источник и снимает category_is_manual."""
    out = StringIO()
    call_command(
        "catalog_distribute_legacy",
        "--source",
        "hoztovary",
        "--exclude-ids",
        str(bag["p"]["fp"].pk),
        "--commit",
        stdout=out,
    )
    snap = out.getvalue().split("Снимок отката:", 1)[1].strip().splitlines()[0].strip()

    call_command("catalog_distribute_legacy", "--rollback", snap, stdout=StringIO())

    for k in ("sad", "krep", "ruch", "plen", "lupa"):
        bag["p"][k].refresh_from_db()
        assert bag["p"][k].category_id == bag["src"].pk
        assert bag["p"][k].category_is_manual is False


@pytest.mark.django_db
def test_dry_run_reports_and_changes_nothing(bag):
    out = StringIO()
    call_command("catalog_distribute_legacy", "--source", "hoztovary", stdout=out)
    text = out.getvalue()

    # Без --exclude-ids: hoz-plenka в источнике = p-plen + p-fp = 2 → Строительный.
    # Всего кластерных в источнике: sad1+krep1+ruch1+plen2+lupa1 = 6 (santeh — non-cluster).
    assert "(sadovaya): move 1" in text
    assert "(stroitelnyy): move 2" in text
    assert "ИТОГО move: 6" in text
    assert "DRY-RUN" in text

    # Ничего не изменилось.
    for p in bag["p"].values():
        p.refresh_from_db()
    assert bag["p"]["sad"].category_id == bag["src"].pk
    assert all(p.category_is_manual is False for p in bag["p"].values())
