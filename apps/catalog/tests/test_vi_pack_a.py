"""VI-INT-06 Pack A: контрактные тесты расширения vi-longtail map.

Три класса проверок (пп.6–8 протокола):
- positive: новые mappings («Квадрат»→drive, «Max усилие»→torque,
  «Количество в наборе»→piece_count, material CrV/Cr-V→crv-steel,
  «полипропилен»→polipropilen) и 10 новых scope tool_type;
- negative fail-closed: «Длина» (unit-trap), «Тип», «Тип инструмента»,
  «Объем», «Материал»=металл/неизвестный, «Min усилие» — НЕ маппятся;
- regression: replay 20 карточек Batch A v2 — 23 safe значений не изменились,
  неожиданных новых маппингов на старые карточки = 0.

DB-free часть гоняется через чистый ``extract_card_values`` против боевой карты
``data/catalog_processing_rules/scraped_attr_map.vi-longtail.json``.
DB-backed (scope-видимость importer'а) — на sandbox/staging окружении.
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
SCOPE_ADDITIONS = {
    "bp-motopompy",
    "bp-nabory-pnevmoinstrumenta",
    "elektronozhnitsy",
    "machete-i-sekachi",
    "miksery",
    "nabory-burov",
    "nabory-pilok",
    "obor-shlangi",
    "otboynye-molotki",
    "zap-filtry",
}


@pytest.fixture(scope="module")
def amap():
    return si.load_attr_map(MAP_PATH)


def _card(attrs):
    return {
        "name": "Карточка источника",
        "brand": "ЗУБР",
        "manufacturer_sku": "X-1",
        "source_url": "https://www.vseinstrumenti.ru/product/x/",
        "attributes": attrs,
    }


def _by_attr(res):
    return {v.attribute_slug: v for v in res.values}


# --- positive (п.6) -----------------------------------------------------------


def test_pack_a_scope_additions_present(amap):
    scope = set(amap["scope_tool_types"])
    assert SCOPE_ADDITIONS <= scope
    assert len(amap["scope_tool_types"]) == 40
    assert set(amap["policy"]["scope_tool_types"]) == scope


def test_kvadrat_maps_to_drive_exact_inch_dict(amap):
    res = si.extract_card_values(_card({"Квадрат": "3/8 дюйма"}), "vseinstrumenti", amap)
    v = _by_attr(res)["drive"]
    assert v.is_option and v.value == "d-3-8"
    res2 = si.extract_card_values(_card({"Квадрат": "1/2 дюйма"}), "vseinstrumenti", amap)
    assert _by_attr(res2)["drive"].value == "d-1-2"


def test_max_usilie_maps_to_torque(amap):
    res = si.extract_card_values(_card({"Max усилие": "210"}), "vseinstrumenti", amap)
    v = _by_attr(res)["torque"]
    assert not v.is_option and v.value == Decimal("210")


def test_kolichestvo_v_nabore_maps_to_piece_count(amap):
    res = si.extract_card_values(_card({"Количество в наборе": "9"}), "vseinstrumenti", amap)
    v = _by_attr(res)["piece_count"]
    assert v.value == Decimal("9")


@pytest.mark.parametrize("raw", ["CrV", "Cr-V"])
def test_crv_alias_variants_resolve_to_single_option(amap, raw):
    res = si.extract_card_values(_card({"Материал": raw}), "vseinstrumenti", amap)
    v = _by_attr(res)["material"]
    assert v.is_option and v.value == "crv-steel"


def test_polipropilen_maps_to_material_option(amap):
    res = si.extract_card_values(_card({"Материал": "полипропилен"}), "vseinstrumenti", amap)
    assert _by_attr(res)["material"].value == "polipropilen"


# --- negative fail-closed (п.7) -----------------------------------------------


@pytest.mark.parametrize("raw", ["100", "50 м", "30 м"])
def test_dlina_never_maps_to_length_or_tape_length(amap, raw):
    """Unit-trap: «Длина» НЕ маппится ни в length, ни в tape_length."""
    res = si.extract_card_values(_card({"Длина": raw}), "vseinstrumenti", amap)
    assert "length" not in _by_attr(res)
    assert "tape_length" not in _by_attr(res)
    assert not any(v.attribute_slug.startswith("length") for v in res.values)


@pytest.mark.parametrize("raw", ["щелчковый", "Torx", "лента"])
def test_tip_never_imported(amap, raw):
    """Generic «Тип» не импортируется вообще (и уж точно не в bit_type)."""
    res = si.extract_card_values(_card({"Тип": raw}), "vseinstrumenti", amap)
    assert "bit_type" not in _by_attr(res)
    assert not res.values


def test_tip_instrumenta_is_not_pav(amap):
    """«Тип инструмента» — taxonomy axis, не PAV и не запись в tool_type."""
    res = si.extract_card_values(_card({"Тип инструмента": "миксер"}), "vseinstrumenti", amap)
    assert "tool_type" not in _by_attr(res)
    assert not res.values


def test_obem_weight_value_not_mapped(amap):
    res = si.extract_card_values(_card({"Объем": "5.8 кг"}), "vseinstrumenti", amap)
    assert not res.values


@pytest.mark.parametrize("raw", ["металл", "вибраниум"])
def test_unknown_material_fails_closed(amap, raw):
    """Незнакомый/шумный материал — dropped, option НЕ создаётся."""
    res = si.extract_card_values(_card({"Материал": raw}), "vseinstrumenti", amap)
    assert "material" not in _by_attr(res)
    assert any("не в словаре опций" in reason for _f, _r, reason in res.dropped)


def test_min_usilie_is_not_torque(amap):
    res = si.extract_card_values(_card({"Min усилие": "10"}), "vseinstrumenti", amap)
    assert "torque" not in _by_attr(res)


# --- Batch A v2 regression (п.8) ----------------------------------------------


def _norm_decimal(s):
    return str(Decimal(str(s)).normalize())


def test_batch_a_v2_replay_unchanged(amap):
    """Расширение карты не меняет интерпретацию 20 карточек Batch A v2.

    Fixture: attributes литерально из 04-batch-a-export-v2.json,
    эталон — отчёт dry-run 04-chars-dryrun-v2.json (created 23 + skipped_voltage 2).
    Проверяем: (1) все 23 safe значения извлекаются так же, как до Pack A;
    (2) дельта extraction над эталоном — ТОЛЬКО задокументированные Pack A
    additions (drive/Квадрат, torque/Max усилие, piece_count/Количество в наборе,
    material crv-steel/polipropilen) — ровно 11 значений, ничего постороннего.
    """
    export = json.loads((FIXTURES_DIR / "vi_pack_a_batch_a_export_v2.json").read_text("utf-8"))
    expected = json.loads((FIXTURES_DIR / "vi_pack_a_chars_dryrun_v2.json").read_text("utf-8"))
    created_by_product = {}
    for c in expected["created"]:
        created_by_product.setdefault(c["product_id"], {})[c["attribute"]] = c["new"]
    skipped_by_product = {}
    for s in expected["skipped_voltage"]:
        skipped_by_product.setdefault(s["product_id"], {})["voltage"] = s["value"]

    pack_a_option_values = {"crv-steel", "polipropilen"}
    pack_a_decimal_attrs = {"torque", "piece_count"}
    delta_total = 0
    for card in export["products"]:
        pid = card["catalog_product_id"]
        res = si.extract_card_values(card, "vseinstrumenti", amap)
        got = {v.attribute_slug: v for v in res.values}
        baseline = {**created_by_product.get(pid, {}), **skipped_by_product.get(pid, {})}
        # (1) эталонная интерпретация сохранилась: всё из created извлекается так же
        for slug, want in created_by_product.get(pid, {}).items():
            assert slug in got, f"product {pid}: потерян {slug}"
            v = got[slug]
            if v.is_option:
                assert str(v.value) == str(want)
            else:
                assert _norm_decimal(v.value) == _norm_decimal(want)
        # (2) дельта — только Pack A additions
        for slug, v in got.items():
            if slug in baseline:
                continue
            delta_total += 1
            if v.is_option:
                assert slug == "material" or slug == "drive", f"product {pid}: чужой {slug}"
                assert (
                    str(v.value) in pack_a_option_values or slug == "drive"
                ), f"product {pid}: {slug}={v.value} вне Pack A"
            else:
                assert slug in pack_a_decimal_attrs, f"product {pid}: чужой {slug}"
    # 12957:3, 12959:3, 22672:2, 22674:2, 36919:1 — задокументированный прирост Pack A
    assert delta_total == 11


# --- DB-backed: scope-видимость importer'а (сandbox/staging) -------------------

ATTRS = {
    "tool_type": (AttributeType.SELECT, ""),
    "drive": (AttributeType.SELECT, ""),
    "torque": (AttributeType.DECIMAL, "Н·м"),
    "material": (AttributeType.SELECT, ""),
    # vi-longtail map управляет всеми этими осями — команда fail-closed требует
    # их наличия в БД (catalog_import_scraped.py:101)
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
    "tool_type": [("miksery", "Миксеры"), ("stanki-zatochnye", "Станки заточные")],
    "drive": [("d-3-8", "3/8"), ("d-1-2", "1/2")],
    "material": [("crv-steel", "Хром-ванадиевая сталь"), ("steel", "Сталь")],
}


@pytest.fixture
def catalog(db):
    cat = Category.add_root(name="Ключи", slug="klyuchi")
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


def _export_v2(tmp_path, cards):
    path = tmp_path / "vi.products.json"
    path.write_text(
        json.dumps({"source": "vseinstrumenti", "products": cards}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(path)


@pytest.mark.django_db
def test_new_scope_type_visible_old_visible_outside_invisible(catalog, tmp_path):
    """miksery (новый scope) и stanki-zatochnye (старый scope) importer видит,
    товар вне расширенного scope — нет."""
    new_p = _product_tt(
        catalog, "Миксер ЗУБР МРД-1400", "miksery", article="МРД-1400", brand="ЗУБР"
    )
    old_p = _product_tt(
        catalog, "Станок СЭМ-10/65 Ресанта", "stanki-zatochnye", article="75/10/3", brand="РЕСАНТА"
    )
    out_p = _product_tt(
        catalog, "Ключ динамометрический KRAFTOOL", "miksery", article="64053-060", brand="KRAFTOOL"
    )
    # у out_p меняем tool_type на несуществующий в scope — эмулируем отсутствие в scope
    out_p.attribute_values.filter(attribute=catalog["attrs"]["tool_type"]).delete()
    cards = [
        {
            "name": "Миксер ЗУБР МРД-1400",
            "brand": "ЗУБР",
            "manufacturer_sku": "МРД-1400",
            "source_url": "https://www.vseinstrumenti.ru/product/a/",
            "attributes": {"Материал": "CrV"},
        },
        {
            "name": "Станок СЭМ-10/65 Ресанта",
            "brand": "РЕСАНТА",
            "manufacturer_sku": "75/10/3",
            "source_url": "https://www.vseinstrumenti.ru/product/b/",
            "attributes": {"Материал": "сталь"},
        },
        {
            "name": "Ключ динамометрический KRAFTOOL",
            "brand": "KRAFTOOL",
            "manufacturer_sku": "64053-060",
            "source_url": "https://www.vseinstrumenti.ru/product/c/",
            "attributes": {"Квадрат": "3/8 дюйма", "Max усилие": "60"},
        },
    ]
    export_path = _export_v2(tmp_path, cards)
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
    assert matched_ids == {new_p.id, old_p.id}
    assert report["stats"]["matched"] == 2
    pav = ProductAttributeValue.objects.filter(
        product=new_p, attribute=catalog["attrs"]["material"]
    )
    assert pav.get().value_option.slug == "crv-steel"
    assert (
        ProductAttributeValue.objects.filter(product=old_p, attribute=catalog["attrs"]["material"])
        .get()
        .value_option.slug
        == "steel"
    )
    assert (
        not ProductAttributeValue.objects.filter(product=out_p)
        .exclude(attribute=catalog["attrs"]["tool_type"])
        .exists()
    )
