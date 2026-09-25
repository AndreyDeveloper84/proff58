"""FOUNDATION-AXES-01: три базовые оси + fail-closed SELECT preflight.

Источник истины — research gate 2026-09-12 (``docs/catalog/2026-09-12-foundation-axes-*.md``)
и exact proposals в ``docs/catalog/appendix/2026-09-12-foundation-axes/``. Кейсы ниже —
реальные названия 1С из ``cases.json`` исследования.

Четыре части:

* A. ``volume`` — «Объём», л; мл → л через ``scale``; тачки с фасетом; бак узла,
  мешки пылесосов и «0,52 мл» — молчание/карантин;
* B. ``package_quantity`` — расширение существующей оси на exact список Tier 1 + Tier 2;
  ``piece_count`` не смешивается; generic «N шт» вне списка — fail closed;
* C. ``linear_length`` — «Длина», м; критерий по КЛАССУ товара: жёсткое изделие в
  метрах остаётся в ``length`` (мм); ``tape_length``/``cable_length`` не тронуты;
* D. preflight ``required options ⊆ AttributeOption`` до ``ImportRun`` (тесты A–E
  владельца) + runtime-guard.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog import attribute_preflight as preflight
from apps.catalog import attribute_quarantine
from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    ImportRun,
    Product,
    ProductAttributeValue,
    Source,
)

# =============================================================================
# Реестры владельцев осей (exact scope FOUNDATION-AXES-01) — закрытые списки
# =============================================================================

VOLUME_OWNERS = {
    "str-kraski",
    "obor-smazka",
    "hoz-tachki",
    "hoz-vedra",
    "hoz-masla",
    "str-germetiki",
    "str-smazki",
    "str-pena",
    "str-klei",
    "str-rastvoriteli",
    "hoz-opryskivateli",
    "svar-ballony",
    "raskhodniki-pajki",
    "fiksatory-germetiki-rezby",
    "hoz-meshki",
    "hoz-himiya",
    "obor-pena",
    "svar-sprei",
    "str-laki",
    "siz-kremy-zashchitnye",
    "hoz-voronki",
    "hoz-ugol-rozzhig",
}
#: Бак/ресивер/контейнер узла и мешки пылесосов — вне оси по решению владельца.
VOLUME_EXCLUDED = {
    "meshki-pylesos",
    "bp-kompressory",
    "bp-generatory",
    "pylesosy",
    "bp-kraskoraspyliteli",
    "kraskoraspyliteli",
    "bp-trimmery",
    "bp-benzopily",
    "bp-motopompy",
    "bp-motobloki",
}
PACKAGE_TIER1 = {"hoz-lezviya", "hoz-trosy", "krep-svp"}
PACKAGE_TIER2 = {
    "krep-zaklepki",
    "krep-gvozdi",
    "krep-samorezy",
    "krep-styazhki",
    "krep-dyubeli",
    "nazhdachka",
    "lenty-shlif",
    "krugi-shlif",
    "pilki-polotna",
    "meshki-pylesos",
    "sterzhni-kleevye",
    "bity",
}
PACKAGE_OWNERS = {"str-skoby"} | PACKAGE_TIER1 | PACKAGE_TIER2
LINEAR_OWNERS = {
    "hoz-trosy",
    "krep-takelazh",
    "siz-rukava",
    "svar-rukava",
    "hoz-shlangi",
    "bp-shlangi",
    "obor-shlangi",
    "bp-leska",
    "termousadka",
    "protyazhki-uzk",
    "hoz-uplotniteli",
    "hoz-truby-fitingi",
    "hoz-plenka",
    "hoz-setki",
    "krep-provoloka",
    "izm-urovni",
}
#: 15 товаров с «0,52 мл»/«0.5 мл» — карантин data_defect (DECISION 3).
DEFECT_052_ML = {
    5474,
    5476,
    5478,
    5479,
    5488,
    5489,
    6280,
    6388,
    6390,
    6393,
    6400,
    6401,
    6402,
    6403,
    31438,
}


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rules(raw) -> AttributeRules:
    return AttributeRules.from_dict(raw)


def _v(rules: AttributeRules, tt: str, axis: str, name: str):
    for value in rules.extract(tt, name):
        if value.slug == axis:
            return value.number
    return None


def _declared(raw: dict, axis: str) -> dict[str, dict]:
    return {
        block["tool_type"]: attr
        for block in raw["tool_types"]
        for attr in block["attributes"]
        if attr["slug"] == axis
    }


# =============================================================================
# A. volume
# =============================================================================


def test_volume_is_declared_exactly_once_per_owner_and_uniformly(raw):
    """Одна canonical-ось: slug ``volume``, «Объём», л, number, regex/40, фильтр."""
    declared = _declared(raw, "volume")
    assert set(declared) == VOLUME_OWNERS
    for tt, attr in declared.items():
        assert (attr["name"], attr["unit"], attr["kind"], attr["source"], attr["priority"]) == (
            "Объём",
            "л",
            "number",
            "regex",
            40,
        ), tt
        assert attr.get("is_filter", True) is True
        assert attr.get("is_ai_feature", False) is False
    # volume_l / volume_ml как отдельные оси не заводятся.
    assert not _declared(raw, "volume_l") and not _declared(raw, "volume_ml")
    # tank_volume — future, в FA-01 не создаётся.
    assert not _declared(raw, "tank_volume")


@pytest.mark.parametrize(
    "tt, name, litres",
    [
        ("hoz-vedra", "Ведро 12л. пластиковое малярное прямоугольное STAYER", "12"),
        ("hoz-vedra", "Ведро 0,8л оцинкованное", "0.8"),
        ("hoz-masla", "Масло моторное 2-х тактное 1 л STIHL HP", "1"),
        ("hoz-masla", "Масло для цепи 946мл OREGON", "0.946"),
        ("str-germetiki", "Герметик силиконовый универсальный 280 мл белый", "0.28"),
        ("str-kraski", "Эмаль ПФ-115 белая 0,9 л", "0.9"),
        ("str-rastvoriteli", "Очиститель монтажной пены 500мл KRAFTOOL KRAFTFLEX", "0.5"),
        ("hoz-opryskivateli", "Опрыскиватель ручной 1,5 л", "1.5"),
        ("obor-smazka", "Масленка GROZ рычажная MP22R/F серии РТ 500мл, трубка+шланг", "0.5"),
        ("svar-sprei", "Спрей антипригарный SIGWELD 520мл без силикона (аэрозоль)", "0.52"),
    ],
)
def test_volume_litres_and_millilitres_land_in_one_axis_in_litres(rules, tt, name, litres):
    assert _v(rules, tt, "volume", name) == Decimal(litres)


def test_volume_wheelbarrow_body_volume_is_the_same_physical_axis(rules, raw):
    """Тачки: «Объём кузова» → ``volume``, фасет разрешён (bind: true), подпись листа."""
    assert _v(rules, "hoz-tachki", "volume", "Тачка садовая 65 л одноколёсная") == Decimal(65)
    attr = _declared(raw, "volume")["hoz-tachki"]
    assert attr.get("bind") is not False
    assert attr["display_name"] == "Объём кузова"
    # Подпись — исключительно контекст листа тачек; Attribute один.
    others = {tt: a for tt, a in _declared(raw, "volume").items() if tt != "hoz-tachki"}
    assert all("display_name" not in a for a in others.values())


@pytest.mark.parametrize(
    "tt, name",
    [
        # Мешки пылесосов: «36 л» — класс совместимых пылесосов, не объём мешка.
        ("meshki-pylesos", "Мешки для пылесоса OZONE 5шт до 36 литров"),
        # Бак/ресивер узла — future tank_volume, здесь молчание.
        ("bp-kompressory", "Компрессор поршневой 24л 220В 1,5кВт 206 л/мин"),
        ("bp-generatory", "Генератор бензиновый 5,5 кВт бак 25л"),
        ("pylesosy", "Пылесос строительный 30 л 1400 Вт"),
    ],
)
def test_volume_stays_silent_for_tank_semantics_and_vacuum_bags(rules, raw, tt, name):
    assert tt in VOLUME_EXCLUDED
    assert tt not in _declared(raw, "volume")
    assert _v(rules, tt, "volume", name) is None


@pytest.mark.parametrize(
    "tt, name",
    [
        # Стоп-проверка манифеста 2026-09-12: та же семантика ВНУТРИ разрешённых типов.
        # Пистолет типизирован как герметик: 310 мл — совместимая туба, не пистолет.
        ("str-germetiki", "Пистолет для герметиков KRAFTOOL 310мл скелетный поворотный"),
        ("str-germetiki", "Пистолет для герметика для туб 600мл ULTIMA"),
        # Бак устройства / совместимая тара у смазочного оборудования.
        ("obor-smazka", "Маслонагнетатель GROZ OLP/16 с баком 16л"),
        ("obor-smazka", "Нагнетатель С-321М 25л 220В"),
        ("obor-smazka", "Установка пневматическая GIGANT для раздачи густой смазки с баком 20л"),
        ("obor-smazka", "Нагнетатель смазки ручной на ведро 20л"),
        # Бачок пеногенератора — тот же класс, что бачок краскопульта.
        ("obor-pena", "Пеногенератор CHAMPION для моек 0,75л"),
        ("obor-pena", "Пеногенератор 50л KRAFTWELL"),
    ],
)
def test_volume_device_tanks_inside_allowed_types_fail_closed(rules, tt, name):
    assert tt in VOLUME_OWNERS
    assert _v(rules, tt, "volume", name) is None


@pytest.mark.parametrize(
    "tt, name, litres",
    [
        # Сама ёмкость — остаётся: маслёнка, шприц, мерная ёмкость, автошампунь, герметик.
        ("obor-smazka", "Масленка GROZ рычажная MP22R/F серии РТ 500мл, трубка+шланг", "0.5"),
        ("obor-smazka", "Шприц GROZ пистолет 500см3, 345 атм, стальн трубка 100мм", "0.5"),
        ("obor-smazka", "Емкость GROZ мерительная MSR/P/F-5 с разметкой, 2 л.", "2"),
        ("obor-pena", "Шампунь для минимоек HUTER усиленный 1л", "1"),
        ("str-germetiki", "Герметик силиконовый универсальный 310мл белый", "0.31"),
    ],
)
def test_volume_containers_next_to_excluded_devices_are_kept(rules, tt, name, litres):
    assert _v(rules, tt, "volume", name) == Decimal(litres)


@pytest.mark.parametrize(
    "tt, name",
    [
        ("hoz-masla", "Масло моторное 4-х тактное 5 л.с. HONDA"),  # лошадиные силы
        ("obor-smazka", "Насос пластиковый 5 л/мин для смазки"),  # расход, не ёмкость
        ("str-germetiki", "Герметик 1л с отвердителем 0.25л"),  # два токена — комплект
        ("hoz-vedra", "Ведро 10-12 л"),  # диапазон
        ("str-kraski", "Эмаль КУДО 601 МЛ-1110 серая"),  # марка эмали
        ("str-kraski", "Набор красок акриловых 12 х 20 мл"),  # набор
    ],
)
def test_volume_traps_fail_closed(rules, tt, name):
    assert _v(rules, tt, "volume", name) is None


@pytest.mark.parametrize(
    "tt, name",
    [
        ("str-kraski", "Грунтовка KUDO KU-2001 серая 0,52мл"),
        ("svar-sprei", "Спрей цинковый, 0.5 мл ЦИНКАЛ ПЛЮС СВАРТОН"),
    ],
)
def test_volume_fractional_millilitres_are_not_normalised(rules, tt, name):
    """«0,52 мл» — опечатка 1С (0,52 л); математикой не чиним: молчание."""
    assert _v(rules, tt, "volume", name) is None


def test_volume_defective_052_ml_products_are_quarantined_as_data_defect(raw):
    managed = {a["slug"] for b in raw["tool_types"] for a in b["attributes"]}
    registry = attribute_quarantine.load_registry(
        data_dir() / attribute_quarantine.FILENAME, managed_slugs=managed
    )
    by_id = {e.product_id: e for e in registry.active}
    assert DEFECT_052_ML <= set(by_id)
    for pid in DEFECT_052_ML:
        entry = by_id[pid]
        assert entry.reason == attribute_quarantine.REASON_DATA_DEFECT
        assert set(entry.attributes) == {"volume"}


# =============================================================================
# B. package_quantity
# =============================================================================


def test_package_quantity_reuses_the_existing_axis_for_the_exact_research_list(raw):
    """Один Attribute (ХАР-20), расширенный ровно на Tier 1 + Tier 2 из proposal."""
    declared = _declared(raw, "package_quantity")
    assert set(declared) == PACKAGE_OWNERS
    for tt, attr in declared.items():
        assert (attr["name"], attr["unit"], attr["kind"]) == (
            "Количество в упаковке",
            "шт.",
            "number",
        ), tt
        # «набор/комплект» глушит новые правила целиком — предметы набора это piece_count
        # (у скоб ХАР-20 та же защита выражена своим skip_regex).
        if tt != "str-skoby":
            assert {"набор", "комплект"} <= set(attr["skip_if"]), tt


@pytest.mark.parametrize(
    "tt, name, qty",
    [
        # Tier 1
        ("hoz-lezviya", "Лезвие 18х100х0,5мм, OLFA сегментированное, 10шт", 10),
        ("hoz-trosy", "Шнур резиновый крепежный 100см ф 8мм 2шт", 2),
        ("krep-svp", "Крестики 2,0 мм 200шт", 200),
        ("krep-svp", "Клинья для кафеля 6 мм STAYER,100 шт", 100),
        # Tier 2 (представительная выборка)
        ("krep-samorezy", "Саморезы по дереву 4,2х76 мм 100 шт", 100),
        ("krep-zaklepki", "Заклепки алюминиевые 4,8х16 мм 50 шт", 50),
        ("pilki-polotna", "Пилки для лобзика T101B 5 шт", 5),
        ("nazhdachka", "Лист шлифовальный 230х280 мм P120 10 шт", 10),
        ("sterzhni-kleevye", "Стержни клеевые 11х200 мм 12 шт", 12),
        ("meshki-pylesos", "Мешки для пылесоса OZONE 5шт до 36 литров", 5),
    ],
)
def test_package_quantity_counts_identical_units_in_the_pack(rules, tt, name, qty):
    assert _v(rules, tt, "package_quantity", name) == Decimal(qty)


def test_package_quantity_is_not_piece_count(rules):
    """«Набор … 114 шт» — предметы набора (``piece_count``), не фасовка."""
    values = {
        v.slug: v.number for v in rules.extract("nabory-otvertok", "Набор отверток и бит 114 шт")
    }
    assert values["piece_count"] == Decimal(114)
    assert "package_quantity" not in values
    # И наоборот: у сменных лезвий нет piece_count.
    lezviya = rules.extract("hoz-lezviya", "Лезвие 18х100х0,5мм, OLFA сегментированное, 10шт")
    assert "piece_count" not in {v.slug for v in lezviya}


@pytest.mark.parametrize(
    "tt, name",
    [
        ("hoz-lezviya", "Нож для рубанка (к-т 4 шт)"),  # к-т → комплект
        ("hoz-lezviya", "яяНож 25 мм 5 лезвий в комплекте"),  # нож с запасными лезвиями
        ("krep-svp", "Зажим+клин 50+50шт"),  # два вида в упаковке
        ("krep-samorezy", "Саморезы 3,5х35 1 кг"),  # весовая фасовка
    ],
)
def test_package_quantity_ambiguous_packs_fail_closed(rules, tt, name):
    assert _v(rules, tt, "package_quantity", name) is None


def test_package_quantity_has_no_global_pieces_mapping(rules, raw):
    """Generic «N шт» вне exact списка не читается — глобального mapping нет."""
    for tt, name in (
        ("molotki", "Молоток слесарный 500 г 2 шт"),
        ("otvertki", "Отвертка крестовая PH2 10 шт"),
        ("hoz-perchatki", "Перчатки х/б 10 пар 20 шт"),
    ):
        assert tt not in PACKAGE_OWNERS
        assert _v(rules, tt, "package_quantity", name) is None


# =============================================================================
# C. linear_length
# =============================================================================


def test_linear_length_is_declared_only_for_the_exact_research_list(raw):
    declared = _declared(raw, "linear_length")
    assert set(declared) == LINEAR_OWNERS
    for tt, attr in declared.items():
        assert (attr["name"], attr["unit"], attr["kind"]) == ("Длина", "м", "number"), tt
    # Единица не входит в имя оси.
    assert all(attr["name"] == "Длина" for attr in declared.values())


@pytest.mark.parametrize(
    "tt, name, metres",
    [
        ("hoz-trosy", 'Трос сантехнический 3м, d6мм ЗУБР"ЭКСПЕРТ" в пласт', "3"),
        ("hoz-trosy", "Трос сантехнический 16мм L=10 метров", "10"),
        ("bp-leska", "Леска д/триммер. 2,4 мм, 245 м, круглая, CHAMPION", "245"),
        ("bp-leska", "Леска R2412 (круг) ф2,4мм 12м", "12"),
        ("siz-rukava", "Рукав пожарный 51 мм 20 м", "20"),
        ("hoz-plenka", "Пленка полиэтиленовая 120 мкм 3м х 100м", "100"),
        ("termousadka", "Трубка термоусадочная ТУТнг-30/15 черная КВТ (50м)", "50"),
        ("hoz-truby-fitingi", "Труба ПНД SDR17 (ПЭ100;10 атм) 100 м", "100"),
        ("izm-urovni", "Гидроуровень 10м", "10"),
    ],
)
def test_linear_length_for_long_goods_is_in_metres(rules, tt, name, metres):
    values = {v.slug: v.number for v in rules.extract(tt, name)}
    assert values["linear_length"] == Decimal(metres)
    # Метры длинномера НЕ пересчитываются в мм-ось.
    assert values.get("length") != Decimal(metres) * 1000


def test_rigid_goods_in_metres_stay_in_length_millimetres_by_product_class(rules, raw):
    """Критерий — класс товара: линейка «0,15 м» → ``length`` = 150 мм, не ``linear_length``."""
    assert "izm-lineyki" not in LINEAR_OWNERS
    values = {v.slug: v.number for v in rules.extract("izm-lineyki", "Линейка стальная 0,15 м")}
    assert values.get("length") == Decimal(150)
    assert "linear_length" not in values
    # Пузырьковый уровень — жёсткий инструмент: якорь «гидроуровень» его не пускает.
    values = {v.slug: v.number for v in rules.extract("izm-urovni", "Уровень алюминиевый 2000 мм")}
    assert values.get("length") == Decimal(2000)
    assert "linear_length" not in values


def test_component_length_axes_are_untouched(raw):
    """``tape_length``/``cable_length`` — оси компонента устройства: остаются, не мигрируют."""
    tape = _declared(raw, "tape_length")
    cable = _declared(raw, "cable_length")
    assert set(tape) == {"izm-ruletki", "hoz-lenty"}
    assert set(cable) == {"udliniteli-filtry", "kabel-provod"}
    for tt in set(tape) | set(cable):
        assert tt not in LINEAR_OWNERS, tt
        assert "linear_length" not in {a["slug"] for a in _block(raw, tt)["attributes"]}


def test_no_global_metres_mapping(rules, raw):
    """«N м» в чужом типе не становится длиной: mapping только tool_type-bounded."""
    for tt, name in (
        ("izm-ruletki", "Рулетка 5 м х 19 мм"),
        ("lomy-gvozdodery", "Лом-гвоздодер 1 м"),
        ("udliniteli-filtry", "Удлинитель 3 розетки 5 м"),
    ):
        assert tt not in LINEAR_OWNERS
        assert _v(rules, tt, "linear_length", name) is None


def _block(raw: dict, tt: str) -> dict:
    return next(b for b in raw["tool_types"] if b["tool_type"] == tt)


# =============================================================================
# D. SELECT preflight — чистые функции
# =============================================================================

TT = "tsangi-i-tsangovye-patrony"
OTHER_TT = "svar-elektrody"

PREFLIGHT_RULES = {
    "source_priority": {"regex": 40, "keyword": 30, "inferred": 10, "manual": 100},
    "tool_types": [
        {
            "tool_type": TT,
            "attributes": [
                {
                    "slug": "tool_kind",
                    "name": "Вид оснастки",
                    "kind": "select",
                    "source": "keyword",
                    "options": [
                        {"value": "Патрон", "slug": "patron", "keywords": ["патрон"]},
                        {"value": "Цанга", "slug": "tsanga", "keywords": ["цанга"]},
                    ],
                },
                {
                    "slug": "diameter",
                    "name": "Диаметр",
                    "kind": "number",
                    "unit": "мм",
                    "source": "regex",
                    "regex": [r"(\d+)\s*мм"],
                },
            ],
        },
        {
            "tool_type": OTHER_TT,
            "attributes": [
                {
                    "slug": "material",
                    "name": "Материал",
                    "kind": "select",
                    "source": "keyword",
                    "options": [
                        {"value": "Алюминий", "slug": "alyuminiy", "keywords": ["алюмин"]},
                    ],
                }
            ],
        },
    ],
}


def test_required_options_are_collected_per_selected_block_only():
    required = preflight.required_select_options(PREFLIGHT_RULES, [TT])
    assert [(r.attribute, r.option, r.value, r.tool_types) for r in required] == [
        ("tool_kind", "patron", "Патрон", (TT,)),
        ("tool_kind", "tsanga", "Цанга", (TT,)),
    ]
    both = preflight.required_select_options(PREFLIGHT_RULES, [TT, OTHER_TT])
    assert {(r.attribute, r.option) for r in both} == {
        ("tool_kind", "patron"),
        ("tool_kind", "tsanga"),
        ("material", "alyuminiy"),
    }


def test_missing_options_are_deterministic_and_complete():
    required = preflight.required_select_options(PREFLIGHT_RULES, [TT, OTHER_TT])
    missing = preflight.check_select_options(required, {"tool_kind": {"patron": object()}})
    assert [(m.attribute, m.option) for m in missing] == [
        ("material", "alyuminiy"),
        ("tool_kind", "tsanga"),
    ]
    text = preflight.format_missing(missing, required=3, tool_types=2)
    assert "material · 'alyuminiy' («Алюминий»)" in text
    assert "tool_kind · 'tsanga' («Цанга»)" in text
    assert "load_attributes" in text
    assert "Обходного флага нет" in text


def test_derive_set_option_outside_options_is_a_ruleset_error():
    doc = json.loads(json.dumps(PREFLIGHT_RULES))
    doc["tool_types"][0]["attributes"][0]["derive"] = {
        "when_present": ["diameter"],
        "set_option": "unknown-opt",
    }
    with pytest.raises(preflight.RulesetError, match="unknown-opt"):
        preflight.required_select_options(doc, [TT])


def test_live_ruleset_passes_the_preflight_lint(raw):
    """Боевой словарь: все derive.set_option объявлены; пары считаются по всем блокам."""
    required = preflight.required_select_options(raw, [b["tool_type"] for b in raw["tool_types"]])
    assert required
    assert all(r.value for r in required)


# =============================================================================
# D. SELECT preflight — контракт команды (тесты A–E владельца)
# =============================================================================


@pytest.fixture
def preflight_rules_path(tmp_path):
    (tmp_path / "attribute_rules.json").write_text(
        json.dumps(PREFLIGHT_RULES, ensure_ascii=False), encoding="utf-8"
    )
    return str(tmp_path)


@pytest.fixture
def schema_without_tsanga(db, preflight_rules_path):
    """Схема «до load_attributes на новых правилах»: у tool_kind есть только patron."""
    top = Category.add_root(name="Оснастка", slug="osnastka", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    tt_opt = AttributeOption.objects.create(attribute=tool_type, value="Цанги", slug=TT)
    other_opt = AttributeOption.objects.create(
        attribute=tool_type, value="Электроды", slug=OTHER_TT
    )
    tool_kind = Attribute.objects.create(
        slug="tool_kind", name="Вид оснастки", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=tool_kind, value="Патрон", slug="patron")
    Attribute.objects.create(
        slug="diameter", name="Диаметр", attribute_type=AttributeType.DECIMAL, unit="мм"
    )
    material = Attribute.objects.create(
        slug="material", name="Материал", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=material, value="Алюминий", slug="alyuminiy")

    def make(name, code, option):
        product = Product.objects.create(category=top, name=name, slug=code, code_1c=code)
        ProductAttributeValue.objects.create(
            product=product, attribute=tool_type, value_option=option, source=Source.MANUAL
        )
        return product

    return {
        "tsanga": make("Цанга 8 мм для фрезера", "c8", tt_opt),
        "patron": make("Патрон цанговый 6 мм", "p6", tt_opt),
        "electrode": make("Электроды алюминиевые 3 мм", "e3", other_opt),
        "tool_kind": tool_kind,
    }


def _enrich(rules_path, *args):
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--path", rules_path, *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def _pav_count(slug: str) -> int:
    return ProductAttributeValue.objects.filter(attribute__slug=slug).count()


@pytest.mark.parametrize("mode", [(), ("--dry-run",)])
def test_B_one_missing_option_fails_before_import_run_in_both_modes(
    schema_without_tsanga, preflight_rules_path, mode
):
    with pytest.raises(CommandError, match=r"tool_kind · 'tsanga' \(«Цанга»\)") as exc:
        _enrich(preflight_rules_path, *mode)
    assert exc.value.returncode == preflight.EXIT_PREFLIGHT == 2
    assert ImportRun.objects.count() == 0
    # Отвергнут ВЕСЬ прогон: даже number-ось того же товара не записана.
    assert _pav_count("diameter") == 0 and _pav_count("tool_kind") == 0
    assert all(not p.attrs_cache for p in Product.objects.all())


def test_C_several_missing_options_are_all_listed(schema_without_tsanga, preflight_rules_path):
    AttributeOption.objects.filter(attribute__slug="material").delete()
    with pytest.raises(CommandError) as exc:
        _enrich(preflight_rules_path)
    text = str(exc.value)
    assert "2 вариантов SELECT" in text
    assert "material · 'alyuminiy'" in text and "tool_kind · 'tsanga'" in text
    assert text.index("material") < text.index("tool_kind")  # детерминированный порядок
    assert ImportRun.objects.count() == 0


def test_D_missing_option_in_an_unrelated_block_does_not_block_the_run(
    schema_without_tsanga, preflight_rules_path
):
    """Электроды (--tool-type) не требуют tsanga: отсутствие в чужом блоке — не отказ."""
    out, err = _enrich(preflight_rules_path, "--tool-type", OTHER_TT)
    assert "Preflight опций: OK — 1 вариантов по 1 типам" in err
    assert ImportRun.objects.get().status == "done"
    assert _pav_count("material") == 1
    assert _pav_count("tool_kind") == 0  # чужой блок не обрабатывался


def test_A_all_options_present_passes_and_writes(schema_without_tsanga, preflight_rules_path):
    AttributeOption.objects.create(
        attribute=schema_without_tsanga["tool_kind"], value="Цанга", slug="tsanga"
    )
    _, err = _enrich(preflight_rules_path)
    assert "Preflight опций: OK — 3 вариантов по 2 типам" in err
    run = ImportRun.objects.get()
    assert run.status == "done"
    assert run.stats["by_attribute"] == {"diameter": 2, "material": 1, "tool_kind": 2}
    tsanga = ProductAttributeValue.objects.get(
        product=schema_without_tsanga["tsanga"], attribute__slug="tool_kind"
    )
    assert tsanga.value_option.slug == "tsanga"


def test_A_load_attributes_then_enrich_is_the_supported_order(
    schema_without_tsanga, preflight_rules_path
):
    """Штатный порядок: load_attributes создаёт tsanga → preflight проходит."""
    call_command("load_attributes", "--path", preflight_rules_path, stdout=StringIO())
    out, err = _enrich(preflight_rules_path, "--dry-run")
    report = json.loads(out)
    rows = [r for r in report["rows"] if r["attribute"] == "tool_kind"]
    assert {r["action"] for r in rows} == {"create"}
    assert not [r for r in report["rows"] if r["action"] == "skip"]


def test_E_option_vanishing_after_preflight_aborts_the_transaction(
    schema_without_tsanga, preflight_rules_path, monkeypatch
):
    """Дрейф между preflight и записью: не skip+continue, а abort всего прогона."""
    AttributeOption.objects.create(
        attribute=schema_without_tsanga["tool_kind"], value="Цанга", slug="tsanga"
    )
    real_check = preflight.check_select_options

    def check_then_drop(required, option_index):
        missing = real_check(required, option_index)
        # Preflight видел полный индекс; после него опция «исчезает» из индекса
        # (эквивалент удаления из БД другим окном).
        option_index["tool_kind"].pop("tsanga")
        return missing

    monkeypatch.setattr(preflight, "check_select_options", check_then_drop)
    with pytest.raises(CommandError, match=r"вариант 'tsanga' \(«Цанга»\).*прогон прерван") as exc:
        _enrich(preflight_rules_path)
    assert exc.value.returncode == 2
    run = ImportRun.objects.get()
    assert run.status == "failed"
    assert "tsanga" in run.stats["error"]
    # Транзакция откатилась целиком: ни одного частичного PAV, кэш пуст.
    assert _pav_count("diameter") == 0 and _pav_count("tool_kind") == 0
    assert _pav_count("material") == 0
    assert all(not p.attrs_cache for p in Product.objects.all())


def test_missing_attribute_is_a_hard_failure_too(db, preflight_rules_path):
    """Тот же класс fail-open: «атрибут не загружен» больше не exit 0."""
    Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    with pytest.raises(CommandError, match="Не найдены атрибуты") as exc:
        _enrich(preflight_rules_path, "--dry-run")
    assert exc.value.returncode == 2
    assert ImportRun.objects.count() == 0


def test_no_write_bypass_flag_exists(preflight_rules_path):
    """Решение владельца: обходного флага для записи нет и не появляется."""
    from apps.catalog.management.commands.enrich_attributes import Command

    parser = Command().create_parser("manage.py", "enrich_attributes")
    flags = {a for action in parser._actions for a in action.option_strings}
    assert not {f for f in flags if "missing" in f or "option" in f or "ignore" in f}, flags
    assert "--force" not in flags and "--allow-missing-options" not in flags


# =============================================================================
# load_attributes: подпись фасета при создании привязки
# =============================================================================

DISPLAY_RULES = {
    "source_priority": {"regex": 40},
    "tool_types": [
        {
            "tool_type": "hoz-tachki",
            "category": "Тележки и тачки",
            "attributes": [
                {
                    "slug": "volume",
                    "name": "Объём",
                    "kind": "number",
                    "unit": "л",
                    "display_name": "Объём кузова",
                    "regex": [r"(\d+)\s*л"],
                }
            ],
        },
        {
            "tool_type": "hoz-vedra",
            "category": "Тара и ёмкости",
            "attributes": [
                {
                    "slug": "volume",
                    "name": "Объём",
                    "kind": "number",
                    "unit": "л",
                    "regex": [r"(\d+)\s*л"],
                }
            ],
        },
    ],
}


def test_display_name_is_set_on_binding_create_only(db, tmp_path):
    (tmp_path / "attribute_rules.json").write_text(
        json.dumps(DISPLAY_RULES, ensure_ascii=False), encoding="utf-8"
    )
    root = Category.add_root(name="Хозтовары", slug="hoz", on_site=True)
    tachki = root.add_child(name="Тележки и тачки", slug="tachki", on_site=True)
    vedra = root.add_child(name="Тара и ёмкости", slug="tara", on_site=True)
    call_command("load_attributes", "--path", str(tmp_path), stdout=StringIO())

    assert Attribute.objects.filter(slug="volume").count() == 1  # Attribute один
    assert CategoryAttribute.objects.get(category=tachki).display_name == "Объём кузова"
    assert CategoryAttribute.objects.get(category=vedra).display_name == ""

    # Владелец переименовал подпись руками — повторный load её не трогает.
    CategoryAttribute.objects.filter(category=tachki).update(display_name="Вместимость")
    call_command("load_attributes", "--path", str(tmp_path), stdout=StringIO())
    assert CategoryAttribute.objects.get(category=tachki).display_name == "Вместимость"
