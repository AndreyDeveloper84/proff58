"""ДРФ-1459 (трек фасетов): ось «Тип съёмника» у листа 172 «Съёмники».

Лист не имел ни одного своего фасета: панель наследовала от родителя 167
только «Тип инструмента». Числовая ось не годится — «число захватов» называют
лишь ~28 % названий; назначение съёмника называет почти каждое.

Замер на стенде 2026-09-07: 88 из 90 опубликованных позиций листа (97 %).
Два непокрытых вообще без ``tool_type`` — правилами по типу недостижимы.

Особенность захода: съёмники лежат в ДВУХ типах — ``syomniki`` (54) и свалке
``prochaya-osnastka`` (34 из 386). Второй блок с тем же ``tool_type`` завести
нельзя (``AttributeRules.from_dict`` индексирует блоки словарём и оставил бы
последний), поэтому ось добавлена в существующий блок свалки и несёт там
собственный адрес привязки и негативный гейт.

Проверяемые границы:

1. **Гейт свалки обязателен.** Без него «Набор стопорных колец 300 предметов»
   получает тип съёмника, будучи самими кольцами, а «Набор гравировальный» и
   «Зажим ручной универсальный» затягиваются словами «набор» и «захват».
2. **Гейт написан по нормализованному названию** — нижний регистр и ё→е,
   поэтому «съемник», а не «съёмник». Иначе он не сработал бы ни разу.
3. **Порядок опций значим.** «Гидравлический» выше «Механического захватного»,
   иначе «Съемник гидравлический 2-х захватный» ушёл бы в механические;
   «Набор съёмников» последний и срабатывает, только когда назначение не названо.
4. **Родовые формы множественного числа.** Пишут «стопорных колец» и
   «стопорного кольца» — форма «кольц» их не покрывает.
5. **Адрес привязки берётся у оси.** Фасет принадлежит листу «Съёмники», а не
   листу 103 блока-свалки, иначе повис бы в «Держателях» пустым.
"""

from __future__ import annotations

import json

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

SYOM, OSN = "syomniki", "prochaya-osnastka"
AXIS = "puller_type"

# название → ожидаемый слаг опции
CASES: list[tuple[str, str]] = [
    ("Съемник стопорных колец 175мм прямой ЗУБР", "stopornyh-kolets"),
    ("Съемник стопорного кольца 160мм загнутый", "stopornyh-kolets"),
    ("Набор съемников стопорных колец 4 пр. СЕРВИС КЛЮЧ", "stopornyh-kolets"),
    ("Съемник масляного фильтра чашка 76мм", "maslyanogo-filtra"),
    ("Съемник масляных фильтров цепной", "maslyanogo-filtra"),
    ("Фильтросъемник краб 60-105мм", "maslyanogo-filtra"),
    ("Съемник поршневых колец 50-100мм", "porshnevyh-kolets"),
    ("Съемник гидравлический 2-х захватный 5т", "gidravlicheskiy"),
    ("Съемник сепараторный 105мм с траверсой", "separatornyy"),
    ("Съемник 2-х 100мм  СЕРВИС КЛЮЧ", "mehanicheskiy-zahvatnyy"),
    ("Съемник 3-х 250мм  СЕРВИС КЛЮЧ", "mehanicheskiy-zahvatnyy"),
    ("Съемник двухзахватный 200мм ЗУБР", "mehanicheskiy-zahvatnyy"),
    ("Съемник подшипников 100мм", "mehanicheskiy-zahvatnyy"),
    ("Набор съемников 12 предметов в кейсе", "nabor-syomnikov"),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _slug(rules: AttributeRules, tool_type: str, name: str) -> str | None:
    for v in rules.extract(tool_type, name):
        if v.slug == AXIS:
            return v.option_slug
    return None


@pytest.mark.parametrize("name,expected", CASES)
def test_named_purpose_becomes_the_axis(rules, name, expected):
    """Назначение съёмника читается из названия у обоих типов одинаково."""
    assert _slug(rules, SYOM, name) == expected
    assert _slug(rules, OSN, name) == expected


def test_retaining_rings_themselves_are_not_a_puller(rules):
    """Главная ловушка захода: «Набор стопорных колец» — это сами кольца.

    Три такие позиции лежат в свалке в листе 405. Без гейта они получили бы
    тип съёмника и попали бы в чужой фасет.
    """
    for name in (
        "Набор стопорных колец 300 предметов",
        "Набор стопорных колец D1.5-22 мм, 300 пр./",
        "Набор стопорных колец D3-32 мм, 300 пр.//С",
    ):
        assert _slug(rules, OSN, name) is None


def test_gate_stops_unrelated_junk_in_the_dump(rules):
    """«набор» и «захват» без съёмника в свалке ловили 25 чужих позиций."""
    for name in (
        "Набор гравировальный 3,2мм, 398 нас.   HAMMER",
        "Набор аксессуаров д/ударн. шурупов. и гайковертов",
        "Зажим ручной универс 150 мм ЗУБР удлиненный",
        "Круг отрезной 24х2,0мм карбид кремния набор",
    ):
        assert _slug(rules, OSN, name) is None


def test_gate_is_written_against_the_normalized_name(rules):
    """Гейт видит текст после ``normalize``: нижний регистр и ё→е.

    Если бы он был написан через «ё», он не сработал бы никогда, и свалка
    осталась бы открытой. Название с «ё» обязано пройти гейт.
    """
    assert _slug(rules, OSN, "Съёмник стопорных колец 175мм") == "stopornyh-kolets"
    assert _slug(rules, OSN, "СЪЕМНИК СТОПОРНЫХ КОЛЕЦ 175ММ") == "stopornyh-kolets"


def test_hydraulic_wins_over_grip_count(rules):
    """Порядок опций: «2-х захватный» не должен перебивать «гидравлический»."""
    assert _slug(rules, SYOM, "Съемник гидравлический 2-х захватный 5т") == "gidravlicheskiy"


def test_set_option_is_the_last_resort(rules):
    """«Набор съёмников» срабатывает, только когда назначение не названо."""
    assert _slug(rules, SYOM, "Набор съемников стопорных колец 4 пр.") == "stopornyh-kolets"
    assert _slug(rules, SYOM, "Набор съемников 12 предметов") == "nabor-syomnikov"


def test_unnamed_purpose_stays_silent(rules):
    """Съёмник без названного назначения обязан дать честный ноль.

    «Съемник универсальный в кейсе» — это съёмник, но какой именно, название
    не говорит. Приписать ему «Набор» только потому, что он в кейсе, значит
    соврать в фасете; 2 непокрытых товара листа — осознанный промах в
    безопасную сторону.
    """
    assert _slug(rules, SYOM, "Съемник универсальный в кейсе") is None
    assert _slug(rules, SYOM, "Съемник ЗУБР Профессионал") is None


def test_genitive_plural_of_ring_is_covered(rules):
    """«колец», а не «кольц»: родовая форма множественного числа.

    Первая редакция правила несла «кольц» и теряла 27 % листа.
    """
    assert _slug(rules, SYOM, "Съемник стопорных колец 175мм") == "stopornyh-kolets"
    assert _slug(rules, SYOM, "Съемник стопорного кольца 160мм") == "stopornyh-kolets"


def test_axis_carries_its_own_binding_address_in_the_dump():
    """Фасет принадлежит листу «Съёмники», а не листу блока-свалки.

    Блок ``prochaya-osnastka`` привязан к «Держателям, адаптерам и патронам»;
    без собственного адреса ось уехала бы туда и висела бы пустым фасетом.
    """
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == OSN)
    axis = next(a for a in block["attributes"] if a["slug"] == AXIS)
    assert block["category"] == "Держатели, адаптеры и патроны"
    assert axis["category"] == "Съёмники"

    own = next(b for b in data["tool_types"] if b["tool_type"] == SYOM)
    assert own["category"] == "Съёмники"
    assert "category" not in own["attributes"][0]


def test_dump_block_keeps_its_original_axis(rules):
    """Ось вида оснастки из прошлого захода не должна была пострадать."""
    assert [r.slug for r in rules.rules_for(OSN)] == ["tool_kind", AXIS]
    assert [r.slug for r in rules.rules_for(SYOM)] == [AXIS]


def test_axis_yields_at_least_two_values():
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    assert len({e for _, e in CASES}) >= 2
