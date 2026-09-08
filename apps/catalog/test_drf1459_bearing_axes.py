"""ДРФ-1459 (трек фасетов): «Тип подшипника» и «Диаметр» у листа «Подшипники».

Лист — бывший 398 «Подшипники и сальники», разделённый по решению владельца
2026-09-08. **Без разделения фасета не получалось:** на смешанном листе из 178
товаров тип подшипника брал 48 %, а наружный диаметр 38 % — обе ниже порога
DRF-1428. Разбавляли их 42 сальника, у которых название это просто артикул
(«Сальник резиновый, тип "О" 301670»), и 25 деталей подшипника.

После разделения на 126 подшипниках: тип **68 %**, диаметр **52 %**.

Радиус нулевой — все 206 товаров типа ``zap-podshipniki`` лежат ровно в этом
листе, за его пределами ни одного.

Проверяемые границы:

1. **Негативный гейт обязателен у ОБЕИХ осей.** Тип несёт не только подшипники,
   но и их детали: «Держатель подшипника», «Крышка подшипника», «Муфта качения
   подшипника», «Ролик подшипника», «Стопор подшипника», «Стальной шарик
   подшипника». Держатель — не подшипник, ролик — не подшипник. Та же болезнь,
   что «Втулка редуктора» в листе 399.
2. **Гейт ловит и чужаков, осевших в листе по слову «подшипник».** Колёса «с
   подшипником», петли «с подшипником», плиткорезы «на подшипниках», обратный
   молоток.
3. **Диаметр берётся НАРУЖНЫЙ.** Порядок шаблонов значим: сначала пара
   «ф32/12мм», где первое число наружное (подшипник 6201 это 12×32×10).
4. **Тройки размеров исключены целиком.** В «Подшипник скольжения 7х11х8»
   первое число — внутренний диаметр, и прочитать его как наружный значит
   соврать. Тип при этом читается как обычно.
5. **Обозначение подшипника осью не делается.** 6202, 608DDW — значений было бы
   под сотню, фасетом это не работает.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "zap-podshipniki"
KIND, DIA = "bearing_type", "diameter"

# название → (тип подшипника, наружный диаметр); None — ось обязана молчать.
CASES: list[tuple[str, str | None, str | None]] = [
    ("Подшипник шариковый   35 мм. 6202VV", "sharikovyy", "35"),
    ("Подшипник шариковый D 47 мм 6005DD", "sharikovyy", "47"),
    ("Подшипник шариковый 19мм (698) 336871", "sharikovyy", "19"),
    ("Подшипник шариковый D24мм 609DDC", "sharikovyy", "24"),
    ("Подшипник шариковый 6001 C3 28мм NSK", "sharikovyy", "28"),
    ("Подшипник роликовый 332983", "rolikovyy", None),
    ("Подшипник роликовый, игольчатый, D14,3мм 939299", "rolikovyy", "14.3"),
    ("Подшипник игольчатый D=6 мм 940917", "igolchatyy", "6"),
    ("Игольчатый подшипник D21мм 985442", "igolchatyy", "21"),
    ("Подшипник скольжения 7х11х8", "skolzheniya", None),
    ("Подшипник 6201 ф32/12мм", None, "32"),
    ("Подшипник 6202 ф35/15мм", None, "35"),
    ("Подшипник 6202", None, None),
    ("Подшипник 6000 ZZ", None, None),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _kind(rules: AttributeRules, name: str) -> str | None:
    for v in rules.extract(TT, name):
        if v.slug == KIND:
            return v.option_slug
    return None


def _dia(rules: AttributeRules, name: str) -> Decimal | None:
    for v in rules.extract(TT, name):
        if v.slug == DIA:
            return v.number
    return None


@pytest.mark.parametrize("name,kind,dia", CASES)
def test_name_yields_both_axes(rules, name, kind, dia):
    """Обе оси читаются из названия подшипника."""
    assert _kind(rules, name) == kind
    assert _dia(rules, name) == (None if dia is None else Decimal(dia))


def test_bearing_part_is_not_a_bearing(rules):
    """Главная ловушка захода: тип несёт и ДЕТАЛИ подшипника.

    Без гейта «Держатель игольчатого подшипника» получил бы тип «Игольчатый»,
    а «Ролик подшипника D8Х20» — диаметр 8 мм.
    """
    for name in (
        "Держатель  игольчатого подшипника (H25PV) 323080",
        "Держатель роликового подшипника 331539",
        "Крышка игольчатого подшипника 323081",
        "Корпус подшипника 324212",
        "Муфта качения подшипника 335249",
        "Ролик подшипника D8Х20 313421",
        "Стопор подшипника 946362",
        "Стальной шарик подшипника шуруповерта 306936",
    ):
        assert _kind(rules, name) is None, name
        assert _dia(rules, name) is None, name


def test_foreign_products_in_the_leaf_stay_silent(rules):
    """Чужаки осели в листе по слову «подшипник» в названии."""
    for name in (
        "Плиткорез 600мм  на подшипниках Remocolor (арт. 46-0-660)",
        "Колесо 3.50*80 D 16 мм с подшипником МАСТЕР",
        "Петля каплевидная с подшипником 20х140мм Tech-Krep",
        "Молоток обратный 6 предм. для внутренних и внешних подшипников",
        "Головка триммерная STURM GT3513-65M усиленный корпус метал подшипник",
        "Набор оправок F-66603: для запрессовки подшипников",
    ):
        assert _kind(rules, name) is None, name
        assert _dia(rules, name) is None, name


def test_pair_yields_the_outer_diameter(rules):
    """«ф32/12мм» — наружный/внутренний: подшипник 6201 это 12×32×10."""
    assert _dia(rules, "Подшипник 6201 ф32/12мм") == Decimal("32")
    assert _dia(rules, "Подшипник 6208 ф80/40мм") == Decimal("80")
    assert _dia(rules, "Подшипник 626 ф19/6мм") == Decimal("19")


def test_triple_size_is_refused_whole(rules):
    """В тройке «7х11х8» первое число — ВНУТРЕННИЙ диаметр.

    Прочитать его как наружный значит соврать, поэтому шаблон не применяется
    целиком. Тип подшипника при этом читается как обычно.
    """
    assert _dia(rules, "Подшипник скольжения 7х11х8") is None
    assert _kind(rules, "Подшипник скольжения 7х11х8") == "skolzheniya"
    assert _dia(rules, "Подшипник шариковый 26х9х8") is None
    assert _kind(rules, "Подшипник шариковый 26х9х8") == "sharikovyy"


def test_designation_is_not_a_diameter(rules):
    """Обозначение подшипника — не размер: 6202 диаметром стать не должно."""
    for name in (
        "Подшипник 6202",
        "Подшипник 6000 ZZ",
        "Подшипник 6008DDU 339063",
        "Подшипник 608 DDW 2100054, Makita",
        "Подшипник 6201 2RS",
        "Подшипник 6907ZZ",
    ):
        assert _dia(rules, name) is None, name


def test_both_axes_carry_the_gate():
    """Гейт объявлен у обеих осей: у одной он ничего не стоил бы."""
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == TT)
    assert block["category"] == "Подшипники"
    for a in block["attributes"]:
        assert a["skip_regex"], a["slug"]
        assert "держател" in a["skip_regex"][0]
    dia = next(a for a in block["attributes"] if a["slug"] == DIA)
    assert len(dia["skip_regex"]) == 2, "второй гейт — тройки размеров"
    assert dia["regex"][0].startswith("ф"), "пара «ф32/12» обязана идти первой"


def test_each_axis_yields_at_least_two_values():
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    assert len({k for _, k, _ in CASES if k}) >= 2
    assert len({d for _, _, d in CASES if d}) >= 2
