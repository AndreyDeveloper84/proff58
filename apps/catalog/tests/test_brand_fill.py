"""BRAND-02: определение бренда-производителя и команда catalog_fill_brand.

Ключевые гарантии: упоминание совместимого бренда НЕ делает его производителем;
писать имеет право единственный статус CREATE; ``changed`` не существует как
исход — занятое поле даёт CONFLICT; dry-run не пишет ничего; сумма статусов
покрывает scope без остатка.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.brand_identity import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_COMPAT,
    IDENTITY_HIGH,
    IDENTITY_NONE,
    decide_brand,
)
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def root(db):
    return Category.add_root(name="Инструмент", slug="tool")


def _p(root, name, **kw):
    defaults = dict(
        category=root,
        name=name,
        slug=f"p{Product.objects.count()}",
        status=ProductStatus.IMPORTED,
        is_active=True,
        price="100",
        available_quantity=5,
    )
    defaults.update(kw)
    return Product.objects.create(**defaults)


# --- совместимость не делает бренд производителем ---------------------------


@pytest.mark.parametrize(
    "name,ref",
    [
        ("Аккумулятор для Makita DF330DWE 10.8В", "MAKITA"),
        ("Оснастка для Bosch GBH 2-26", "BOSCH"),
        ("Щётки угольные, совместим с DeWALT DW9057", "DEWALT"),
        ("Патрон подходит для ЗУБР ЗДУ-780", "ЗУБР"),
        ("Щетки угольные АНАЛОГ 5х10х14мм 18-120 MAKITA CB325", "MAKITA"),
    ],
)
def test_compatibility_reference_is_not_manufacturer(name, ref):
    d = decide_brand(name)
    assert d.status == IDENTITY_COMPAT, name
    assert d.brand == ""
    assert ref in d.compatibility_refs


def test_manufacturer_wins_over_compatibility_reference():
    """«KRAFTOOL … для Makita» — производитель KRAFTOOL, Makita лишь совместимость.

    Маркер обязан исключать контекстное упоминание, а не товар целиком.
    """
    d = decide_brand("Бита KRAFTOOL PH2х50 мм для Makita DF330")
    assert d.status == IDENTITY_HIGH
    assert d.brand == "KRAFTOOL"
    assert d.compatibility_refs == ("MAKITA",)


@pytest.mark.parametrize(
    "name,brand",
    [
        # «для металла» — назначение, бренд правее остаётся производителем
        ("Круг отрезной для металла 125х1,6х22,2 ЗУБР", "ЗУБР"),
        # найдено аудитом dry-run: мягкое окно помечало эти товары совместимостью,
        # хотя предлог относится к предмету («для бит», «для коронок»), а не к бренду
        ("Адаптер  для бит KRAFTOOL BULLDOG 150мм с жесткой автомат фиксацией", "KRAFTOOL"),
        ("Адаптер для биметал.коронок ЗУБР SDS+ d 14-30 мм", "ЗУБР"),
        ('Адаптер 1/4"F-3/8"M увеличивающий для головок KRAFTOOL', "KRAFTOOL"),
    ],
)
def test_purpose_preposition_does_not_block_manufacturer(name, brand):
    """Маркер смежности действует, только если бренд — прямой объект предлога."""
    d = decide_brand(name)
    assert d.status == IDENTITY_HIGH, name
    assert d.brand == brand


def test_two_manufacturers_are_ambiguous():
    d = decide_brand("Набор ЗУБР и KRAFTOOL в кейсе")
    assert d.status == IDENTITY_AMBIGUOUS
    assert d.brand == ""
    assert set(d.manufacturers) == {"ЗУБР", "KRAFTOOL"}


def test_no_brand():
    assert decide_brand("Шпилька резьбовая 10х1000 цинк").status == IDENTITY_NONE


def test_series_is_not_a_brand():
    """ALLIGATOR/EXPERT — линейки внутри бренда, самостоятельным брендом не считаются."""
    d = decide_brand("Ножовка Alligator GIPS 7 550мм спец зуб")
    assert d.status == IDENTITY_NONE


# --- команда ----------------------------------------------------------------


@pytest.mark.django_db
def test_dry_run_writes_nothing(root, tmp_path):
    p = _p(root, "Бита KRAFTOOL PH2х50")
    report = tmp_path / "r.json"
    call_command("catalog_fill_brand", "--json-report", str(report))
    p.refresh_from_db()
    assert p.brand == ""
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["counts"]["CREATE"] == 1
    assert data["written"] == 0


@pytest.mark.django_db
def test_apply_writes_only_create(root, tmp_path):
    good = _p(root, "Бита KRAFTOOL PH2х50")
    compat = _p(root, "Аккумулятор для Makita DF330DWE")
    none = _p(root, "Шпилька резьбовая 10х1000 цинк")
    artifact = tmp_path / "rb.json"
    call_command("catalog_fill_brand", "--apply", "--rollback-artifact", str(artifact))
    good.refresh_from_db()
    compat.refresh_from_db()
    none.refresh_from_db()
    assert good.brand == "KRAFTOOL"
    assert compat.brand == ""
    assert none.brand == ""


@pytest.mark.django_db
def test_existing_brand_never_overwritten_and_reported_as_conflict(root, tmp_path):
    """changed не существует: занятое поле — CONFLICT, а не тихий update."""
    p = _p(root, "Бита KRAFTOOL PH2х50", brand="ЗУБР")
    report = tmp_path / "r.json"
    call_command(
        "catalog_fill_brand",
        "--apply",
        "--rollback-artifact",
        str(tmp_path / "rb.json"),
        "--json-report",
        str(report),
    )
    p.refresh_from_db()
    assert p.brand == "ЗУБР"
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["counts"]["CONFLICT"] == 1
    assert data["counts"]["CREATE"] == 0


@pytest.mark.django_db
def test_same_brand_already_set_is_keep(root, tmp_path):
    p = _p(root, "Бита KRAFTOOL PH2х50", brand="KRAFTOOL")
    report = tmp_path / "r.json"
    call_command("catalog_fill_brand", "--json-report", str(report))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["counts"]["KEEP"] == 1
    assert data["counts"]["CONFLICT"] == 0
    p.refresh_from_db()
    assert p.brand == "KRAFTOOL"


@pytest.mark.django_db
def test_statuses_cover_scope_without_remainder(root, tmp_path):
    for name in (
        "Бита KRAFTOOL PH2х50",
        "Аккумулятор для Makita DF330DWE",
        "Набор ЗУБР и KRAFTOOL в кейсе",
        "Шпилька резьбовая 10х1000 цинк",
    ):
        _p(root, name)
    report = tmp_path / "r.json"
    call_command("catalog_fill_brand", "--json-report", str(report))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert sum(data["counts"].values()) == data["scope"]["total"] == 4
    assert data["counts"] == {
        "CREATE": 1,
        "KEEP": 0,
        "CONFLICT": 0,
        IDENTITY_COMPAT: 1,
        IDENTITY_AMBIGUOUS: 1,
        IDENTITY_NONE: 1,
    }


@pytest.mark.django_db
def test_apply_requires_rollback_artifact(root):
    _p(root, "Бита KRAFTOOL PH2х50")
    with pytest.raises(CommandError):
        call_command("catalog_fill_brand", "--apply")


@pytest.mark.django_db
def test_rollback_artifact_keeps_old_value(root, tmp_path):
    """Артефакт обязан хранить прежнее значение, иначе откат неотличим от «не было»."""
    p = _p(root, "Бита KRAFTOOL PH2х50")
    artifact = tmp_path / "rb.json"
    call_command("catalog_fill_brand", "--apply", "--rollback-artifact", str(artifact))
    items = json.loads(artifact.read_text(encoding="utf-8"))["items"]
    assert items == [{"product_id": p.id, "old_brand": "", "new_brand": "KRAFTOOL"}]


@pytest.mark.django_db
def test_scope_flags(root, tmp_path):
    _p(root, "Бита KRAFTOOL PH2х50", available_quantity=0)
    _p(root, "Бита STAYER PH2х50", available_quantity=3)
    report = tmp_path / "r.json"
    call_command(
        "catalog_fill_brand", "--in-stock-only", "--active-only", "--json-report", str(report)
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["scope"]["total"] == 1
    assert data["by_brand"] == {"STAYER": 1}
