"""VI-INT-16 Pure Scope Expansion: regression coverage (+5 scope tool_type).

По pattern test_vi_pack_a.py. Доказывает:
- positive: extraction существующих source fields 5 новых типов → существующие
  mappings → существующие canonical Attributes (без новой semantics);
- voltage negative: все 4 кейса non-battery (220 / 220/230) → PROTECTED
  (skipped_voltage по production-правилу, НЕ CREATE);
- generic fail-closed: «Тип», «Тип инструмента», «Длина», «Класс товара»,
  «Цвет», «Механизм», «Min усилие», «Объем» не импортируются и после
  расширения (Package A не превращается в B/C/D);
- select: unknown value → dropped, option не создаётся;
- unit: значения S1 — прямые единицы, конверсий нет;
- negative control: boltorezy НЕ в новом scope.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.catalog import scraped_import as si
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)

MAP_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "catalog_processing_rules"
    / "scraped_attr_map.vi-longtail.json"
)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
NEW_SCOPE_TYPES = {
    "payalniki",
    "stameski",
    "stanki-derevoobrabatyvayushchie",
    "sverlilnye-stanki",
    "ustanovki-almaznogo-bureniya",
}


@pytest.fixture(scope="module")
def amap():
    return si.load_attr_map(MAP_PATH)


@pytest.fixture(scope="module")
def cards():
    raw = json.loads((FIXTURES_DIR / "vi_scope_expansion_cards.json").read_text("utf-8"))
    return {c["product_id"]: c for c in raw}


def _by_attr(res):
    return {v.attribute_slug: v for v in res.values}


# --- scope -------------------------------------------------------------------


def test_new_scope_types_present_exact(amap):
    scope = set(amap["scope_tool_types"])
    assert NEW_SCOPE_TYPES <= scope
    assert len(scope) == 45
    assert "boltorezy" not in scope  # negative control


# --- positive extraction по 5 типам ------------------------------------------


def test_payalniki_extraction(amap, cards):
    res = si.extract_card_values(cards[24740], "vseinstrumenti", amap)
    got = _by_attr(res)
    assert got["power"].value == Decimal("40")
    assert got["weight_kg"].value == Decimal("0.136")


def test_stameski_extraction(amap, cards):
    res = si.extract_card_values(cards[33229], "vseinstrumenti", amap)
    assert _by_attr(res)["weight_kg"].value == Decimal("1.31")


def test_stanki_derevo_extraction(amap, cards):
    res = si.extract_card_values(cards[44908], "vseinstrumenti", amap)
    got = _by_attr(res)
    assert got["power"].value == Decimal("800")
    assert got["diameter"].value == Decimal("200")
    assert got["bore"].value == Decimal("30")
    assert got["weight_kg"].value == Decimal("13.4")


def test_sverlilnye_stanki_extraction(amap, cards):
    res = si.extract_card_values(cards[44928], "vseinstrumenti", amap)
    got = _by_attr(res)
    assert got["width"].value == Decimal("225")
    assert got["height"].value == Decimal("580")
    assert got["weight_kg"].value == Decimal("16.4")


def test_ustanovki_extraction(amap, cards):
    res = si.extract_card_values(cards[44985], "vseinstrumenti", amap)
    assert _by_attr(res)["weight_kg"].value == Decimal("23")


# --- voltage negative: все 4 кейса → PROTECTED --------------------------------

VOLTAGE_CASES = [24740, 44908, 44928, 44985]


@pytest.mark.parametrize("pid", VOLTAGE_CASES)
def test_voltage_non_battery_is_protected_not_create(amap, cards, pid):
    """Production rule (scraped_import._plan + is_battery_values): voltage на
    не-battery товаре (>=60 В и нет power_source=battery) → skipped_voltage
    ВСЕГДА. Доказываем на extraction-уровне: значение >= 60 и признак battery
    отсутствует → plan обязан пропустить, не создать."""
    res = si.extract_card_values(cards[pid], "vseinstrumenti", amap)
    got = _by_attr(res)
    assert "voltage" in got
    v = got["voltage"]
    assert v.value >= 60
    assert not si.is_battery_values(res.values)


def test_voltage_battery_still_written(amap):
    """Контроль обратной стороны: батарейное напряжение (18 В) защиту НЕ ломает."""
    res = si.extract_card_values({"attributes": {"Напряжение": "18"}}, "vseinstrumenti", amap)
    assert si.is_battery_values(res.values)


# --- generic fail-closed -------------------------------------------------------

GENERIC_FIELDS = [
    ("Тип", "щелчковый"),
    ("Тип инструмента", "миксер"),
    ("Длина", "100"),
    ("Класс товара", "Профессиональный"),
    ("Цвет", "черный"),
    ("Механизм", "щелчковый"),
    ("Min усилие", "10"),
    ("Объем", "5.8 кг"),
]


@pytest.mark.parametrize("field,raw", GENERIC_FIELDS)
def test_generic_fields_never_imported(amap, field, raw):
    res = si.extract_card_values({"attributes": {field: raw}}, "vseinstrumenti", amap)
    assert not res.values


def test_unknown_select_fails_closed(amap):
    res = si.extract_card_values(
        {"attributes": {"Покрытие": "вибраниум-покрытие"}}, "vseinstrumenti", amap
    )
    assert "coating" not in _by_attr(res)
    assert any("не в словаре опций" in reason for _f, _r, reason in res.dropped)


# --- unit: прямые единицы, конверсий нет --------------------------------------


def test_units_are_direct_no_conversion(amap):
    res = si.extract_card_values(
        {
            "attributes": {
                "Мощность": "800",
                "Вес нетто": "13.4",
                "Диаметр": "200",
                "Ширина": "225",
                "Количество в наборе": "7",
                "Max усилие": "210",
            }
        },
        "vseinstrumenti",
        amap,
    )
    got = _by_attr(res)
    assert got["power"].value == Decimal("800")
    assert got["weight_kg"].value == Decimal("13.4")
    assert got["diameter"].value == Decimal("200")
    assert got["width"].value == Decimal("225")
    assert got["piece_count"].value == Decimal("7")
    assert got["torque"].value == Decimal("210")


# --- negative control: boltorezy вне scope ------------------------------------


def test_boltorezy_out_of_scope(amap):
    assert "boltorezy" not in set(amap["scope_tool_types"])
    assert "boltorezy" not in set(amap["policy"]["scope_tool_types"])


# --- DB-backed: scope-видимость importer'а (CI/sandbox) ------------------------

ATTRS = {
    "tool_type": (AttributeType.SELECT, ""),
    "drive": (AttributeType.SELECT, ""),
    "torque": (AttributeType.DECIMAL, "Н·м"),
    "material": (AttributeType.SELECT, ""),
    "bore": (AttributeType.DECIMAL, "мм"),
    "coating": (AttributeType.SELECT, ""),
    "diameter": (AttributeType.DECIMAL, "мм"),
    "disc_diameter": (AttributeType.DECIMAL, "мм"),
    "height": (AttributeType.DECIMAL, "мм"),
    "motor_type": (AttributeType.SELECT, ""),
    "piece_count": (AttributeType.DECIMAL, "шт"),
    "power": (AttributeType.DECIMAL, "Вт"),
    "power_source": (AttributeType.SELECT, ""),
    "voltage": (AttributeType.DECIMAL, "В"),
    "weight_kg": (AttributeType.DECIMAL, "кг"),
    "width": (AttributeType.DECIMAL, "мм"),
}
OPTIONS = {
    "tool_type": [
        ("payalniki", "Паяльники"),
        ("stameski", "Стамески"),
        ("stanki-derevoobrabatyvayushchie", "Станки деревообрабатывающие"),
        ("sverlilnye-stanki", "Сверлильные станки"),
        ("ustanovki-almaznogo-bureniya", "Установки алмазного бурения"),
        ("boltorezy", "Болторезы"),
        ("nabory-klyuchey-imbusovyh", "Наборы ключей имбусовых"),
    ],
    "drive": [("d-3-8", "3/8"), ("d-1-2", "1/2")],
    "material": [("crv-steel", "Хром-ванадиевая сталь"), ("steel", "Сталь")],
}


@pytest.fixture
def catalog(db):
    cat = Category.add_root(name="Инструмент", slug="instrument")
    attrs = {
        slug: Attribute.objects.create(slug=slug, name=slug, attribute_type=atype, unit=unit)
        for slug, (atype, unit) in ATTRS.items()
    }
    opts = {}
    for slug, values in OPTIONS.items():
        for oslug, value in values:
            opts[(slug, oslug)] = AttributeOption.objects.create(
                attribute=attrs[slug], value=value, slug=oslug
            )
    return {"category": cat, "attrs": attrs, "opts": opts}


def _product_tt(catalog, name, tt_slug, **kw):
    defaults = dict(
        category=catalog["category"],
        name=name,
        slug=f"p{Product.objects.count()}",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    defaults.update(kw)
    p = Product.objects.create(**defaults)
    ProductAttributeValue.objects.create(
        product=p,
        attribute=catalog["attrs"]["tool_type"],
        value_option=catalog["opts"][("tool_type", tt_slug)],
        source=Source.RULES,
    )
    return p


def _export(tmp_path, cards):
    path = tmp_path / "vi.products.json"
    path.write_text(
        json.dumps({"source": "vseinstrumenti", "products": cards}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(path)


@pytest.mark.django_db
def test_new_scope_types_visible_boltorezy_not_and_22673_confirm(catalog, tmp_path):
    """5 новых типов importer видит; boltorezy — нет; 22673 piece_count=7 —
    CONFIRM (уже применён), не CREATE."""
    p_solder = _product_tt(
        catalog, "Паяльник 40 Вт ЗУБР", "payalniki", article="55405-40_z01", brand="ЗУБР"
    )
    p_stameski = _product_tt(
        catalog, "Набор стамесок 5пр ЗУБР", "stameski", article="18097-H5", brand="ЗУБР"
    )
    p_bolt = _product_tt(
        catalog, "Болторез 750мм ЗУБР", "boltorezy", article="23311-075_z01", brand="ЗУБР"
    )
    p_22673 = _product_tt(
        catalog,
        "Набор ключей СЕРВИС КЛЮЧ",
        "nabory-klyuchey-imbusovyh",
        article="76430",
        brand="СЕРВИС КЛЮЧ",
    )
    ProductAttributeValue.objects.create(
        product=p_22673,
        attribute=catalog["attrs"]["piece_count"],
        value_decimal=7,
        source=Source.SCRAPER,
    )
    cards = json.loads((FIXTURES_DIR / "vi_scope_expansion_cards.json").read_text("utf-8"))
    cards = [c for c in cards if c["product_id"] in (24740, 33229, 31957)]
    cards.append(
        {
            "name": "Набор ключей СЕРВИС КЛЮЧ 7пр",
            "brand": "СЕРВИС КЛЮЧ",
            "manufacturer_sku": "76430",
            "source_url": "https://www.vseinstrumenti.ru/product/x/",
            "attributes": {"Количество в наборе": "7"},
        }
    )
    export_path = _export(tmp_path, cards)
    report_path = tmp_path / "report.json"
    call_command(
        "catalog_import_scraped",
        export_path,
        "--category",
        "vi-longtail",
        "--report",
        str(report_path),
        verbosity=0,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    matched_ids = {m["product_id"] for m in report["matched"]}
    assert p_solder.id in matched_ids
    assert p_stameski.id in matched_ids
    assert p_22673.id in matched_ids
    assert p_bolt.id not in matched_ids  # boltorezy вне scope
    # voltage 24740 (220, non-battery) — PROTECTED, не CREATE
    assert not ProductAttributeValue.objects.filter(
        product=p_solder, attribute=catalog["attrs"]["voltage"]
    ).exists()
    assert (
        ProductAttributeValue.objects.filter(product=p_solder, attribute=catalog["attrs"]["power"])
        .get()
        .value_decimal
        == 40
    )
    # 22673 piece_count=7 → CONFIRM, второй записи нет
    assert (
        ProductAttributeValue.objects.filter(
            product=p_22673, attribute=catalog["attrs"]["piece_count"]
        ).count()
        == 1
    )
    assert (
        not ProductAttributeValue.objects.filter(product=p_bolt)
        .exclude(attribute=catalog["attrs"]["tool_type"])
        .exists()
    )
