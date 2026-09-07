"""ДРФ-1459 (трек фасетов): ось «Вид инструмента» у листа «Держатели, адаптеры и патроны».

Лист 103 не имел фасета. Числовая ось не подходит: диапазон зажима называют
только 19 патронов из 54 в наличии, это 35 %. Зато вид оснастки называет почти
каждое название — патрон, оправка, втулка переходная, кольцо переходное,
держатель бит, цанговый патрон.

Ось ``tool_kind`` **существующая** (127 значений), в ней уже были «Держатель» и
«Переходник (адаптер)» — нового атрибута не заводим, добавляются опции.

Замер на стенде 2026-09-07: 77/83 = 92 %, 7 различных значений.

Проверяемые границы:

1. **Порядок опций значим.** «Патрон быстрозажимной 1-10мм **с адаптером** на
   1/4"» обязан читаться как патрон: `patron` стоит выше общего
   `perehodnik-adapter`. «Держатель бит» — выше по той же причине.
2. **Радиус правила на свалочном типе замерен до написания.**
   ``prochaya-osnastka`` держит 386 опубликованных позиций по всему каталогу;
   правило срабатывает на 91 (23 %), из них 53 в листе 103, 34 в «Прочей
   оснастке», 4 в свёрлах и кругах — и все они действительно патроны и оправки.
3. **Узкое слово у широкого типа.** ``zap-shpindeli-valy`` держит ещё шпиндели,
   валы и стволы; ключевое слово «цанговый патрон» не пускает их в ось.
"""

from __future__ import annotations

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

AXIS = "tool_kind"

CASES: list[tuple[str, str, str | None]] = [
    # --- prochaya-osnastka ---
    ("prochaya-osnastka", 'Патрон для дрели быстрозажимной 1,5-13мм резьба 1/2" ЗУБР', "Патрон"),
    ("prochaya-osnastka", "Патрон для дрели ключевой 3-16 мм. B16 СЕБ", "Патрон"),
    ("prochaya-osnastka", "Оправка с лапкой КМ2/В10 СТАЛЬ 40Х, ГОСТ 2682-86", "Оправка"),
    ("prochaya-osnastka", "Втулка переходная 5/4 СТАЛЬ 40Х,  ГОСТ 13598-85", "Втулка переходная"),
    ("prochaya-osnastka", "Переходник с SDS+ на патрон ЗУБР МАСТЕР", "Патрон"),
    ("prochaya-osnastka", "Адаптер с SDS-max на SDS+ ЗУБР МАСТЕР", "Переходник (адаптер)"),
    ("prochaya-osnastka", "Зажим цанговый 6 мм", None),
    # --- переходные кольца: свой тип ---
    ("perehodnye-koltsa", "Кольцо переходное 32х25,4 для дисков", "Кольцо переходное"),
    ("perehodnye-koltsa", "Кольцо переходное 22,23х20 для дисков", "Кольцо переходное"),
    # --- цанговые патроны у широкого типа ---
    ("zap-shpindeli-valy", "Цанговый патрон 12мм для M12 325199", "Цанговый патрон"),
    ("zap-shpindeli-valy", 'Цанга патрона 1/2" для M12', "Цанговый патрон"),
    ("zap-shpindeli-valy", "Шпиндель в сборе 6698112", None),
    ("zap-shpindeli-valy", "Ствол отбойного молотка", None),
    # --- держатели бит ---
    ("osnastka-bit", 'Держатель бит МАГНИТ 200мм 1/4"  HiKoki', "Держатель бит"),
    ("osnastka-bit", "Держатель бит  для шуруповерта", "Держатель бит"),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _kind(rules: AttributeRules, tool_type: str, name: str) -> str | None:
    for v in rules.extract(tool_type, name):
        if v.slug == AXIS:
            return v.option_value
    return None


@pytest.mark.parametrize(
    "tool_type,name,expected", CASES, ids=[f"{t}:{n[:34]}" for t, n, _ in CASES]
)
def test_holder_kind_from_real_names(rules, tool_type, name, expected):
    assert _kind(rules, tool_type, name) == expected


def test_chuck_with_adapter_is_still_a_chuck(rules):
    """«Патрон быстрозажимной с адаптером на 1/4"» — патрон, а не переходник."""
    name = 'Патрон быстрозажимной 1-10мм с адаптером на 1/4"'
    assert _kind(rules, "prochaya-osnastka", name) == "Патрон"


def test_spindles_do_not_become_chucks(rules):
    """Тип zap-shpindeli-valy держит шпиндели и стволы — они не патроны."""
    for name in ("Шпиндель 6698112", "Вал промежуточный 325199", "Ствол в сборе"):
        assert _kind(rules, "zap-shpindeli-valy", name) is None, name


def test_axis_yields_at_least_two_values(rules):
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    got = {_kind(rules, t, n) for t, n, e in CASES if e is not None}
    assert len(got - {None}) >= 2


def test_axis_absent_for_unrelated_type(rules):
    """Ось не протекает в чужие типы."""
    assert all(r.slug != AXIS for r in rules.rules_for("nozhi"))


def test_adapter_option_reuses_existing_slug(rules):
    """Слаг «Переходник (адаптер)» — существующий `adapter`.

    В ``tool_kind`` эта опция уже есть с 12 значениями. Новый слаг с тем же
    ярлыком дал бы в фасете два одинаковых пункта — дефект, видимый покупателю.
    """
    rule = next(r for r in rules.rules_for("prochaya-osnastka") if r.slug == AXIS)
    opt = next(o for o in rule.options if o.value == "Переходник (адаптер)")
    assert opt.slug == "adapter", f"слаг разошёлся с существующим: {opt.slug}"
