"""SEO-BATCH-03: мощность УШМ из обозначения модели, когда в названии есть пробел.

Правило обозначения для `bolgarki-ushm` существовало и раньше, но требовало дробь без
пробелов: «УШМ-125/ 900» и «УШМ-П125- 755» мимо него проходили. Кейсы взяты с названий
стенда (76 УШМ) в форме 1С — именно её подаёт `enrich_attributes`.

Граница: явные ватты в тексте идут первым regex и всегда побеждают обозначение —
у ЗУБРа обозначение и мощность намеренно расходятся («УШМ-125-1205Э … 1200Вт»).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "bolgarki-ushm"


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _power(rules, name):
    for v in rules.extract(TT, name):
        if v.slug == "power":
            return v.number
    return None


CASES = [
    # обозначение с пробелом — то, ради чего правка
    ("Шлифмаш угл РЕСАНТА УШМ-125/ 900", 900),
    ("Шлифмаш угл ЗУБР ПРОФ УШМ-П125- 755 125мм", 755),
    # обозначение без пробела продолжает работать
    ("Шлифмаш угл РЕСАНТА УШМ-125/1100", 1100),
    ("Шлифмаш полир РЕСАНТА УШМ-180/1500П", 1500),
    ("Шлифмаш угл ИНТЕРСКОЛ УШМ-230/2100М", 2100),
    # явные ватты в тексте сильнее обозначения
    ("Шлифмаш угл ЗУБР УШМ-125-1205Э 125мм, 1200Вт", 1200),
    ("Шлифмаш угл ЗУБР ПРОФ УШМ-П230-2400 ПВ, 230мм 1400Вт", 1400),
    ("Шлифмаш угл ЗУБР ПРОФ УШМ-П125- 755 125мм, 750Вт фланец МИГ компакт", 750),
    # диаметр круга не является мощностью
    ("Шлифмашина угловая аккумуляторная 125 мм без АКБ", None),
]


@pytest.mark.parametrize(("name", "expected"), CASES)
def test_ushm_power_from_designation(rules, name, expected):
    got = _power(rules, name)
    if expected is None:
        assert got is None, f"{name!r}: лишняя мощность {got!r}"
    else:
        assert got == Decimal(str(expected)), f"{name!r}: {got!r} != {expected!r}"
