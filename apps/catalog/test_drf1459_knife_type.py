"""ДРФ-1459 (трек фасетов): ось «Тип ножа» у листа «Ножи и лезвия».

Лист 353 показывал покупателю только панель типа — ни одного фильтра. Числовые
оси порога DRF-1428 не берут и взять не могут: ``width`` — ширина сменного
сегментного лезвия (13 из 38 в наличии, 34 %), ``length`` — длина складного или
сапожного ножа (8 из 38, 21 %). Это разные физические величины у разных видов
ножа, и свести их в одну ось нельзя. Дотянуть ``width`` тоже нечем: у
непокрытых ширины в названии просто нет — «Нож универсальный с автостопом»,
«Нож электрика 1000В, лезвие 50мм» (50 — длина лезвия), «Нож для рубанка 92мм».

Зато вид ножа называет **каждое** название: замер на стенде 2026-09-07 дал
38/38 в наличии и 9 различных значений — порог пройден с запасом.

Проверяемые границы:

1. **Порядок опций значим.** SELECT возвращает первое совпадение ключевого
   слова, поэтому «Нож монтерский, СКЛАДНОЙ, изогнутое лезвие» обязан читаться
   как монтёрский, а не складной. То же у ножа электрика.
2. **Сегментный выводится через ``derive`` от ``width``.** У большинства таких
   ножей слова «сегмент» в названии нет — только «Нож 18 мм». Закрытый список
   9/18/20/25 мм в оси ``width`` это промышленный стандарт сменного лезвия, и
   его наличие само по себе означает сегментный нож.
3. **Числовые оси остаются на месте** — новая ось их не подменяет и не ломает.
"""

from __future__ import annotations

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TOOL_TYPE = "nozhi"
AXIS = "knife_type"

# Реальные названия листа 353 (в наличии, замер 2026-09-07).
NAMES: list[tuple[str, str | None]] = [
    ("Лезвие крюковидное KRAFTOOL BlackMax-S24 10шт", "lezvie-smennoe"),
    ("Лезвие крюковидное KRAFTOOL Solinger S24 5шт", "lezvie-smennoe"),
    ("Нож для рубанка с адаптером 92мм (арт. 100008A)", "dlya-rubanka"),
    ("Нож для напольных покрытий KRAFTOOL LINO тип А02", "dlya-pokrytiy"),
    ("Нож электрика 1000В, лезвие 50мм, прорез.ручка", "elektrika"),
    ("Нож электрика диэлектрический KN-1 KRAFTOOL прямой", "elektrika"),
    ("Нож электрика диэлектрический KN-7 KRAFTOOL с пяткой изогнутый", "elektrika"),
    ("Нож монтерский, складной, изогнутое лезвие, STAYER Professional", "monterskiy"),
    ("Нож монтерский, складной, прямое лезвие, STAYER Professional", "monterskiy"),
    ("Нож сапожный, 180 мм, ЗУБР", "sapozhnyy"),
    ("Нож сапожный, 185 мм, ЗУБР", "sapozhnyy"),
    ("Нож канцелярский с зажимом прорезь на рукоятке белый", "kantselyarskiy"),
    ("Нож канцелярский с зажимом прорезь на рукоятке черный", "kantselyarskiy"),
    ("Нож 18 мм KRAFTOOL UNI с сегмент лезвием", "segmentnyy"),
    ("Нож 18 мм ЗУБР М-18А с автостопом", "segmentnyy"),
    ("Нож 18 мм MIRAX обрезинен с винт фиксатором", "segmentnyy"),
    ("Нож 25 мм KRAFTOOL GRAND-25 с двойным фиксатором", "segmentnyy"),
    ("Нож  9мм ЗУБР ПРО-9А, металлический с автостоп ПРОФ", "segmentnyy"),
    ("Нож POWERBULT складной 155мм с клинком Drop Point", "skladnoy"),
    ("Нож POWERBULT складной 212мм с клинком Drop Point", "skladnoy"),
    ("Нож универсальный KRAFTOOL с автостопом", "universalnyy"),
    ("Нож универсальный ЗУБР А24 с трапециевидным лезвием", "universalnyy"),
    ("Нож POWERBULT 10 в 1 многофункциональный", "universalnyy"),
    ("Нож POWERBULT 13 в 1 многофункциональный", "universalnyy"),
    # варианты написания и кухонные — добавлены после замера всего листа
    ("Нож монтера (Металлист)", "monterskiy"),
    ('Нож для линолеума усиленный "Дельфин" с автоматической подачей', "dlya-pokrytiy"),
    ("Нож LEGIONER 200мм шеф-повар", "kuhonnyy"),
    ("Нож LEGIONER  90мм овощной", "kuhonnyy"),
    ("Нож LEGIONER 190мм сантоку", "kuhonnyy"),
    # честно неоднозначные — вид не назван, ось молчит
    ("Нож строительный нержавеющий в чехле", None),
    ("Нож монтажный GROSS", None),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _kind(rules: AttributeRules, name: str) -> str | None:
    for v in rules.extract(TOOL_TYPE, name):
        if v.slug == AXIS:
            return v.option_slug
    return None


@pytest.mark.parametrize("name,expected", NAMES, ids=[n[:46] for n, _ in NAMES])
def test_knife_type_from_real_names(rules, name, expected):
    assert _kind(rules, name) == expected


def test_monterskiy_wins_over_skladnoy(rules):
    """«Нож монтерский, складной» — монтёрский это вид, складной лишь свойство."""
    assert _kind(rules, "Нож монтерский, складной, прямое лезвие, STAYER") == "monterskiy"


def test_segmentnyy_inferred_from_width(rules):
    """Слова «сегмент» нет, но ширина из закрытого ряда 9/18/20/25 говорит сама."""
    name = "Нож 18 мм ЗУБР ТИТАН-А металлический обрезиненный"
    vals = {v.slug: v for v in rules.extract(TOOL_TYPE, name)}
    assert "width" in vals, "ширина обязана извлечься — на ней держится вывод"
    assert vals[AXIS].option_slug == "segmentnyy"
    assert vals[AXIS].source == "inferred"


def test_numeric_axes_survive(rules):
    """Новая ось не подменяет и не ломает существующие width и length."""
    v = {x.slug: x for x in rules.extract(TOOL_TYPE, "Нож 25мм ЗУБР ТИТАН-25 с автостоп")}
    assert str(v["width"].number) == "25"
    v = {x.slug: x for x in rules.extract(TOOL_TYPE, "Нож сапожный, 185 мм, ЗУБР")}
    assert str(v["length"].number) == "185"


def test_axis_yields_at_least_two_values(rules):
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    got = {_kind(rules, n) for n, _ in NAMES}
    assert len(got - {None}) >= 2


def test_axis_absent_for_other_types(rules):
    """Ось живёт только у ножей."""
    assert all(r.slug != AXIS for r in rules.rules_for("krugi-shlif"))


def test_kitchen_knives_are_not_construction(rules):
    """Кухонные ножи лист держит, но строительным инструментом они не являются."""
    assert _kind(rules, "Нож LEGIONER 200мм нарезочный") == "kuhonnyy"
    assert _kind(rules, "Нож 18 мм ЗУБР М-18А с автостопом") == "segmentnyy"


def test_unnamed_kind_stays_silent(rules):
    """Если вид не назван — ось молчит, а не угадывает."""
    assert _kind(rules, "Нож строительный, нерж.сталь, прорезиненная ручка") is None
    assert _kind(rules, "Стальная подкладка под ножи (1 пара) 314740") is None
