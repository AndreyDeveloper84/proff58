"""ДРФ-1524: дефекты, которые нашла сверка dry-run уже ПОСЛЕ правок batch-2.

Гейт-цикл устроен так, что правки правил проверяются не на придуманных строках,
а на полном пуле стенда. Прогон по семи исправленным типам дал 1563 значения, и
сверка «значение против смысла названия» остановила ещё четыре случая — из них
три чинятся правилами, четвёртый правилами не чинится в принципе и ушёл в
карантин (см. `data/attribute_quarantine.json`, товар 34721).

Все четыре — не повторение batch-2, а другие классы:
число из соседней ВЕЛИЧИНЫ того же типоразмера, падеж ключевого слова, чужой
товар внутри типа и ошибка в самих данных 1С.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _v(rules: AttributeRules, tt: str, axis: str, name: str):
    for v in rules.extract(tt, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


# --- 1. Наборы: дюймовый диапазон размеров принят за привод -------------------


@pytest.mark.parametrize(
    "name",
    [
        'Набор комб. 11 пр  ( 1/4"-7/8" ) FORCE',
        'Набор комб.14 пр. (5/16"-1-1/4") KING TONY',
    ],
)
def test_inch_size_range_is_not_a_drive(rules, name):
    """«1/4"-7/8"» — размеры рожковой части, а не привод.

    У набора комбинированных ключей привода нет вообще: привод есть у головок и
    трещоток. Дробь в названии выглядит ровно как привод, поэтому ось молчит по
    всему классу «набор комб», а не по этим двум именам.
    """
    assert _v(rules, "nabory-instrumenta", "drive", name) is None


def test_real_drives_are_untouched(rules):
    """Регресс: и одиночный привод, и комбинация читаются как прежде."""
    tt = "nabory-instrumenta"
    assert _v(rules, tt, "drive", 'Набор инструмента 21пр., 1/2" АвтоДело') == "d-1-2"
    assert _v(rules, tt, "drive", "Набор инструмента 101 пр 1/4- 1/2  HiKoki") == "d-1-4-1-2"


# --- 2. Наборы: вид набора решался падежом ключевого слова ---------------------


@pytest.mark.parametrize(
    "name",
    [
        "Набор инструментов торцевые головки STAYER 10 пред",
        'Набор инструментов торцевые головки STAYER 1/4" 10 предмет',
        "Набор инструмента  20 предметов торцевые головки STAYER 8-",
        "Набор инструмента  10 предметов STURM головки HEX 4-19",
        "Набор инструмента  13 предметов STURM головки TORX 8-70",
    ],
)
def test_socket_set_is_not_universal(rules, name):
    """Опция ловила только родительный падеж, а в данных — именительный.

    «торцевых»/«головок» против «торцевые головки»: ключевое слово «набор
    инструмент» выигрывало, и набор головок уезжал в «Универсальный». На витрине
    это значит, что фильтр «Торцевые головки» их не покажет.
    """
    assert _v(rules, "nabory-instrumenta", "set_kind", name) == "sockets"


def test_mixed_set_stays_universal(rules):
    """«головки 4-11мм + биты» — там и то, и другое: обобщение здесь верно."""
    tt = "nabory-instrumenta"
    name = 'Набор инструмента  44 предмета 1/4" головки 4-11мм + биты'
    assert _v(rules, tt, "set_kind", name) == "universal"
    assert _v(rules, tt, "set_kind", "Набор инструмента 45пр  СЕРВИС КЛЮЧ") == "universal"


# --- 3. Шурупы: чужой товар внутри типа ---------------------------------------


def test_screwdriver_bit_is_not_a_screw(rules):
    """«Насадка для шуруповерта ТУНДРА d4-19мм» отдавала диаметр 4.

    Это оснастка, а не шуруп: товар лежит в типе krep-shurupy ошибочно.
    Перетипизация — отдельный трек, а ось закрыта здесь, чтобы до тех пор не
    писать ложь на живую карточку.
    """
    name = "Насадка для шуруповерта ТУНДРА d4-19мм, для снятия фаски на бо"
    assert _v(rules, "krep-shurupy", "diameter", name) is None
    assert _v(rules, "krep-shurupy", "length", name) is None


def test_real_screws_still_read(rules):
    """Регресс: стоп-слово не задевает настоящие шурупы."""
    tt = "krep-shurupy"
    assert _v(rules, tt, "diameter", "Шуруп с шестигранной головкой 10х140") == Decimal("10")
    assert _v(rules, tt, "length", "Шуруп с шестигранной головкой 10х140") == Decimal("140")


# --- 4. Струбцина с перевёрнутыми границами — карантин, а не правило ----------


def test_inverted_bounds_come_from_the_name_itself(rules):
    """«900-800мм» читается дословно, и это правильное поведение движка.

    Границы перевёрнуты в САМОМ названии 1С. Развернуть пару молча нельзя:
    порядок чисел в названии определить нечем, и там, где порядок верен, разворот
    исказил бы данные. Поэтому правило не трогали, а товар 34721 закрыт записью в
    `data/attribute_quarantine.json` — лечение в 1С, не в regex.
    """
    name = 'Струбцина ручная пистолетная, пласт.корпус 900-800мм, 150кгс KRAFTOOL "EcoKraft"'
    assert _v(rules, "strubtsiny", "clamp_from", name) == Decimal("900")
    assert _v(rules, "strubtsiny", "clamp_to", name) == Decimal("800")


def test_quarantine_entry_for_that_clamp_exists(rules):
    """Гейт держится записью реестра — без неё ложь уехала бы в БД."""
    import json

    registry = json.loads((data_dir() / "attribute_quarantine.json").read_text(encoding="utf-8"))
    entry = next(i for i in registry["items"] if i["product_id"] == 34721)
    assert entry["status"] == "active"
    assert set(entry["attributes"]) == {"clamp_from", "clamp_to"}


# --- 5. Коронки: ось была неверна во всех 10 оставшихся случаях ----------------
#
# batch-2 закрыл удлинители и «свыше N мм», но сверка на ПОЛНОМ пуле показала ещё
# четыре причины. Каждая — отдельный класс, и ни одна не видна на придуманных
# строках: все четыре живут в том, как 1С записывает названия.


@pytest.mark.parametrize(
    "name",
    [
        "яяАдаптер для коронок HITCHI до 30мм 11,0 мм-ый шест",
        "яяАдаптер для коронок HITCHI до 30мм 9,5 мм-ый шести",
        "яяАдаптер для коронок HITCHI свыше 40 мм 11,0 мм-ый",
        "яяАдаптер для коронок HITCHI свыше 40мм 9,5 мм-ый ше",
    ],
)
def test_truncated_name_still_gates_the_shank_size(rules, name):
    """Названия в 1С обрезаны до 50 символов, и стоп-слово не доезжает.

    «…11,0 мм-ый шест» — от «шестигранника» осталось четыре буквы, поэтому
    skip_if по нему не срабатывает. Гейт перенесён на форму «N мм-ый», которая
    помещается в обрезок всегда и означает размер ХВОСТОВИКА, а не коронки.
    """
    assert _v(rules, "osnastka-koronok", "diameter", name) is None


@pytest.mark.parametrize(
    "name",
    [
        "яяАдаптер для коронок HITCHI свыше  40 мм 9,5 мм-ый",
        "яяАдаптер для коронок HITCHI свыше  40 мм SDS+",
    ],
)
def test_double_space_after_svyshe_is_gated_too(rules, name):
    """«свыше  40 мм» — два пробела, и один lookbehind их не покрывает.

    Lookbehind в Python фиксированной ширины, поэтому вариант с двойным пробелом
    объявлен отдельно. Иначе граница совместимости уезжает в диаметр.
    """
    assert _v(rules, "osnastka-koronok", "diameter", name) is None


def test_hex_shank_adapter_is_gated(rules):
    """«Переходник с 6-гр.хвостовиком 8 мм» — снова хвостовик, а не коронка."""
    name = "яяПереходник с 6-гр.хвостовиком 8 мм без центрирующе"
    assert _v(rules, "osnastka-koronok", "diameter", name) is None


@pytest.mark.parametrize(
    "name",
    [
        'яяУдлинитель 1 1/4" 300мм',
        "яяУдлинитель 500мм для коронок алмазных М16",
    ],
)
def test_service_prefix_does_not_disable_the_stop_word(rules, name):
    """Префикс «яя» отключал стоп-слово: «яяУдлинитель» не даёт границы слова.

    skip_if требует ГРАНИЦЫ НАЧАЛА СЛОВА — это защита от «БОЕКОМПЛЕКТ», и она
    правильная. Побочный эффект: служебный префикс, приклеенный вплотную, эту
    границу убирает, и стоп-слово молчит. Движок не трогали: «удлинител»
    продублировано в skip_regex, который сверяется обычным поиском по regex.
    Чинить надо названия, а не механизм границы.
    """
    assert _v(rules, "osnastka-koronok", "diameter", name) is None


def test_extension_keeps_mount_and_shank_despite_the_gate(rules):
    """Гейт снимает только диаметр — посадка и хвостовик остаются."""
    tt = "osnastka-koronok"
    name = "яяУдлинитель для коронок алмазных М16 SDS-MAX  460мм"
    assert _v(rules, tt, "mount", name) == "m16"
    assert _v(rules, tt, "shank_type", name) == "sds-max"


def test_real_adapter_diameter_survives_all_four_gates(rules):
    """Регресс: настоящий диаметр переходника не задет ни одним из гейтов."""
    assert _v(rules, "osnastka-koronok", "diameter", "Переходник для коронок М16, 100 мм") == (
        Decimal("100")
    )


def test_compatibility_mention_is_not_the_product_itself(rules):
    """«для удлинителей» — упоминание совместимости, а не сам удлинитель.

    Стоп-проверка гейт-цикла поймала это как ложный PRUNE: голое «удлинител» в
    skip_regex гасило «Сверло центрирующее 8х110мм … для удлинителей», где
    диаметр 8 верный и УЖЕ БЫЛ ЗАПИСАН. Первый dry-run промаха не показывал —
    skip_if «удлинитель» родительный падеж не ловит вовсе («удлинителей» не
    содержит «удлинитель»), поэтому дефект появился ровно вместе с правкой.
    Паттерн привязан к началу названия.
    """
    name = "Сверло центрирующее 8х110мм конический хвост ЗУБР для удлинителей"
    assert _v(rules, "osnastka-koronok", "diameter", name) == Decimal("8")
