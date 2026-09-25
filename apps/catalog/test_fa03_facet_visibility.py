"""FOUNDATION-AXES-03: пять слабых фасетов FA-01 больше не материализуются (HIDE_FOR_NOW).

Решение владельца 2026-09-12 по итогам FA-02 (read-only facet exposure audit): из 21
привязки FA-01 пять скрываются — ``bind: false`` в боевом словаре. Это **visibility
decision, а не отказ от оси**: извлечение работает, накопленные PAV остаются, Attribute
и правила не трогаются. Тесты ниже держат ровно три инварианта:

* negative — на боевом словаре ``load_attributes`` НЕ создаёт пять привязок;
* positive — контрольные KEEP_VISIBLE привязки создаются как прежде (217 — с подписью
  «Объём кузова»);
* extraction — ``bind: false`` не отключает правило: значения извлекаются и PAV живут.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    Source,
)

#: HIDE_FOR_NOW — (tool_type, ось, имя листа) ровно как в FA-02 decision table.
HIDDEN = (
    ("bity", "package_quantity", "Биты"),
    ("krugi-shlif", "package_quantity", "Круги"),
    ("krep-dyubeli", "package_quantity", "Дюбели"),
    ("meshki-pylesos", "package_quantity", "Мешки-пылесборники"),
    ("siz-kremy-zashchitnye", "volume", "Кремы и средства защиты кожи"),
)
#: Positive controls KEEP_VISIBLE.
CONTROLS = (
    ("bp-leska", "linear_length", "Леска для триммера", ""),
    ("krep-samorezy", "package_quantity", "Саморезы", ""),
    ("pilki-polotna", "package_quantity", "Пильная оснастка", ""),
    ("obor-smazka", "volume", "Смазочное оборудование", ""),
    ("hoz-tachki", "volume", "Тележки и тачки", "Объём кузова"),
    ("str-germetiki", "volume", "Герметики и монтажные пены", ""),
)
#: Извлечение у скрытых типов — реальные названия 1С из FA-01 manifest.
EXTRACTION_CASES = (
    ("bity", "package_quantity", "Биты MKSS Toolbox PH2х127мм торсионная магнитная (10 шт)", 10),
    ("krugi-shlif", "package_quantity", "Круг шлиф. 125мм Р 80 5шт, на велюр основе", 5),
    ("krep-dyubeli", "package_quantity", "Дюбель-гвоздь 7,3х42мм для пневмопистолета 100шт", 100),
    (
        "meshki-pylesos",
        "package_quantity",
        "Мешок-пылесборник синтетический OZONE 5шт до 36 литров",
        5,
    ),
    ("siz-kremy-zashchitnye", "volume", 'Крем для рук универсальный "ЭЛЕН", 100мл', Decimal("0.1")),
)


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))


def _axis(raw: dict, tt: str, slug: str) -> dict:
    block = next(b for b in raw["tool_types"] if b["tool_type"] == tt)
    return next(a for a in block["attributes"] if a["slug"] == slug)


# --- словарь ------------------------------------------------------------------


def test_exactly_the_five_hidden_axes_are_bind_false_and_still_extract(raw):
    """Ровно пять ``bind: false`` из FA-03; правило при этом полноценное (regex на месте)."""
    for tt, slug, _ in HIDDEN:
        axis = _axis(raw, tt, slug)
        assert axis["bind"] is False, (tt, slug)
        assert axis["regex"], (tt, slug)  # extraction не отключено
    for tt, slug, _, _ in CONTROLS:
        assert _axis(raw, tt, slug).get("bind") is not False, (tt, slug)
    # Никаких других bind:false среди трёх осей сверх тех, что были в FA-01 proposal:
    # считаем только по листам решения — в новых блоках FA-03 не появляется.
    fa03 = {
        (b["tool_type"], a["slug"])
        for b in raw["tool_types"]
        for a in b["attributes"]
        if a.get("bind") is False and "FOUNDATION-AXES-03" in a.get("_note", "")
    }
    assert fa03 == {(tt, slug) for tt, slug, _ in HIDDEN}


@pytest.mark.parametrize("tt, slug, name, expected", EXTRACTION_CASES)
def test_bind_false_does_not_disable_extraction(tt, slug, name, expected):
    rules = AttributeRules.from_file(data_dir() / "attribute_rules.json")
    values = {v.slug: v.number for v in rules.extract(tt, name)}
    assert values[slug] == Decimal(expected)


# --- load_attributes на боевом словаре ---------------------------------------


@pytest.fixture
def leaves(db):
    """Живые листья с именами из решения (только они: остальные категории словаря —
    штатное not_found, предупреждение без --strict-bindings)."""
    root = Category.add_root(name="Каталог", slug="katalog", on_site=True)
    made = {}
    for _, _, name in HIDDEN:
        made[name] = root.add_child(name=name, slug=f"h-{len(made)}", on_site=True)
    for _, _, name, _ in CONTROLS:
        made[name] = root.add_child(name=name, slug=f"c-{len(made)}", on_site=True)
    Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    return made


def _plan_bindings(rules_dir) -> list[dict]:
    out = StringIO()
    call_command("load_attributes", "--path", rules_dir, "--dry-run", stdout=out, stderr=StringIO())
    return json.loads(out.getvalue())["bindings"]


def test_plan_never_materializes_the_five_hidden_bindings(leaves):
    rows = {(r["category"], r["attribute"]): r for r in _plan_bindings(str(data_dir()))}
    for _, slug, name in HIDDEN:
        assert (name, slug) not in rows, (name, slug)
    for _, slug, name, display in CONTROLS:
        row = rows[(name, slug)]
        assert row["action"] == "create" and row["status"] == "bound", (name, slug)
        assert row["target"].get("display_name", "") == display


def test_apply_creates_controls_but_not_hidden_and_keeps_existing_pav(leaves):
    """Apply на боевом словаре: контроли привязаны, пять скрытых — нет, PAV нетронуты."""
    call_command("load_attributes", "--path", str(data_dir()), stdout=StringIO(), stderr=StringIO())
    for _, slug, name in HIDDEN:
        assert not CategoryAttribute.objects.filter(
            category=leaves[name], attribute__slug=slug
        ).exists(), (name, slug)
    for _, slug, name, display in CONTROLS:
        ca = CategoryAttribute.objects.get(category=leaves[name], attribute__slug=slug)
        assert ca.is_filter is True and ca.display_name == display

    # Накопленное значение скрытой оси живёт независимо от привязки.
    tool_type = Attribute.objects.get(slug="tool_type")
    bity = AttributeOption.objects.create(attribute=tool_type, value="Биты", slug="bity")
    product = Product.objects.create(
        category=leaves["Биты"],
        name="Биты MKSS Toolbox PH2х127мм торсионная магнитная (10 шт)",
        slug="bity-10",
        code_1c="bity-10",
    )
    ProductAttributeValue.objects.create(
        product=product, attribute=tool_type, value_option=bity, source=Source.MANUAL
    )
    pav = ProductAttributeValue.objects.create(
        product=product,
        attribute=Attribute.objects.get(slug="package_quantity"),
        value_decimal=Decimal(10),
        source=Source.REGEX,
        confidence=100,
    )
    call_command("load_attributes", "--path", str(data_dir()), stdout=StringIO(), stderr=StringIO())
    pav.refresh_from_db()
    assert pav.value_decimal == Decimal(10) and pav.source == Source.REGEX
    assert not CategoryAttribute.objects.filter(
        category=leaves["Биты"], attribute__slug="package_quantity"
    ).exists()
