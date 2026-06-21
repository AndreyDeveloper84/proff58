"""Тесты движка извлечения характеристик (attribute_extract) и команды покрытия."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Product,
    ProductAttributeValue,
)

RULES_PATH = Path(settings.BASE_DIR) / "data" / "attribute_rules.json"
TT = "dreli-shurupoverty"


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(RULES_PATH)


def _by_slug(rules: AttributeRules, name: str):
    return {v.slug: v for v in rules.extract(TT, name)}


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Дрель 18В", 18),
        ("Шуруповёрт 18V", 18),
        ("Дрель 20V Max", 20),
        ("Шуруповёрт 12 Volt", 12),
        ("Дрель 18-вольтовый", 18),
        ("Аккумулятор 21.6 В", Decimal("21.6")),
    ],
)
def test_voltage_variants(rules, name, expected):
    v = _by_slug(rules, name).get("voltage")
    assert v is not None and v.number == Decimal(str(expected))


def test_voltage_does_not_match_wattage(rules):
    # «800 Вт» — мощность, не напряжение: «в» внутри «вт» не должно ловиться.
    assert "voltage" not in _by_slug(rules, "Дрель ударная 800 Вт")


def test_voltage_ignores_watts_written_as_v(rules):
    # 1С пишет ватты как «В» без «т»: «230мм 2000В» = 2000 Вт, не напряжение.
    # Напряжение инструмента ≤ 99 В, поэтому 3-значные «В» (ватты/сеть) не берём.
    assert "voltage" not in _ushm(rules, "Шлифмаш угл ЗУБР УШМ-П230-2000 П, 230мм 2000В")
    assert "voltage" not in _perf(rules, "Перфоратор 230В сетевой")


@pytest.mark.parametrize("name", ["Дрель 55 Нм", "Дрель 55Нм", "Drill 55 Nm", "Drill 55NM"])
def test_torque_variants(rules, name):
    v = _by_slug(rules, name).get("torque")
    assert v is not None and v.number == Decimal("55")


@pytest.mark.parametrize("name", ["АКБ 4 Ач", "АКБ 4Ah", "АКБ 2.0 Ач"])
def test_battery_capacity_variants(rules, name):
    v = _by_slug(rules, name).get("battery_capacity")
    assert v is not None and v.number is not None


def test_power_source_select(rules):
    assert _by_slug(rules, "Дрель аккумуляторная").get("power_source").option_slug == "battery"
    assert _by_slug(rules, "Дрель сетевая").get("power_source").option_slug == "mains"


def test_motor_type_brushless_before_brushed(rules):
    # «бесщёточная» содержит подстроку «щеточн» — порядок вариантов важен.
    assert _by_slug(rules, "Дрель бесщёточная").get("motor_type").option_slug == "brushless"
    assert _by_slug(rules, "Дрель щёточный двигатель").get("motor_type").option_slug == "brushed"


def test_battery_included_boolean(rules):
    assert _by_slug(rules, "Шуруповёрт без АКБ").get("battery_included").boolean is False
    assert _by_slug(rules, "Шуруповёрт с АКБ").get("battery_included").boolean is True
    assert "battery_included" not in _by_slug(rules, "Шуруповёрт сетевой")  # не угадываем


def test_priority_from_rules(rules):
    v = _by_slug(rules, "Дрель 18В").get("voltage")
    assert v.source == "regex" and v.priority == 40


def test_full_name_multiple_attributes(rules):
    found = _by_slug(rules, "Дрель-шуруповёрт Bosch GSR 18V 55 Нм бесщёточная без АКБ")
    assert found["voltage"].number == Decimal("18")
    assert found["torque"].number == Decimal("55")
    assert found["motor_type"].option_slug == "brushless"
    assert found["battery_included"].boolean is False


# --- Перфораторы (tool_type=perforatory) -------------------------------------

PERF = "perforatory"


def _perf(rules: AttributeRules, name: str):
    return {v.slug: v for v in rules.extract(PERF, name)}


def test_perforatory_full_name_sds_plus(rules):
    found = _perf(rules, "Перфоратор SDS-plus 800Вт 2.7Дж")
    assert found["power"].number == Decimal("800")
    assert found["impact_energy"].number == Decimal("2.7")
    assert found["chuck_type"].option_slug == "sds-plus"


def test_perforatory_full_name_sds_max(rules):
    found = _perf(rules, "Перфоратор SDS-max 1500Вт 10Дж")
    assert found["power"].number == Decimal("1500")
    assert found["impact_energy"].number == Decimal("10")
    assert found["chuck_type"].option_slug == "sds-max"


def test_perforatory_chuck_type_max_not_confused_with_plus(rules):
    # «SDS-max» не должен классифицироваться как «sds-plus» (порядок вариантов).
    assert _perf(rules, "Перфоратор SDS-max").get("chuck_type").option_slug == "sds-max"
    assert _perf(rules, "Перфоратор SDS-plus").get("chuck_type").option_slug == "sds-plus"


def test_perforatory_power_does_not_match_voltage(rules):
    # «800Вт» — мощность, не напряжение: «в» внутри «вт» не ловится.
    found = _perf(rules, "Перфоратор 800Вт")
    assert found["power"].number == Decimal("800")
    assert "voltage" not in found


def test_perforatory_voltage_for_cordless(rules):
    # Аккумуляторный кейс: напряжение извлекается.
    assert _perf(rules, "Перфоратор аккумуляторный 18В").get("voltage").number == Decimal("18")


def test_perforatory_kilowatt_not_supported(rules):
    # Движок без unit-множителя: «1.2кВт» НЕ даёт power (известное поведение, follow-up).
    assert "power" not in _perf(rules, "Перфоратор 1.2кВт")


# --- Болгарки/УШМ (tool_type=bolgarki-ushm) ----------------------------------

USHM = "bolgarki-ushm"


def _ushm(rules: AttributeRules, name: str):
    return {v.slug: v for v in rules.extract(USHM, name)}


def test_ushm_corded_full_name(rules):
    found = _ushm(rules, "Шлифмаш угл Bosch GWS 17-125CIE; 1700Вт, d=125мм, 11000 об/мин")
    assert found["power"].number == Decimal("1700")
    assert found["disc_diameter"].number == Decimal("125")
    assert found["no_load_speed"].number == Decimal("11000")


def test_ushm_disc_diameter_variants(rules):
    assert _ushm(rules, "УШМ d=230 мм").get("disc_diameter").number == Decimal("230")
    assert _ushm(rules, "Болгарка 115мм").get("disc_diameter").number == Decimal("115")
    assert _ushm(rules, "Шлифмаш угл ЗУБР AB-80 ф82мм").get("disc_diameter").number == Decimal("82")


def test_ushm_disc_diameter_only_canonical_with_mm(rules):
    # Некатегорийный размер «16мм» (как в щётках 7х17х16мм) не должен матчиться.
    assert "disc_diameter" not in _ushm(rules, "Щетки угольные 7х17х16мм болгарка")
    # Размер в модели без «мм» осознанно не берём (precision-first).
    assert "disc_diameter" not in _ushm(rules, "Шлифмаш угл Makita DGA504RF")


def test_ushm_disc_diameter_keyword_context(rules):
    # Размер по контексту «диск/круг/под» + канон — без «мм».
    assert _ushm(rules, "УШМ под диск 125 ЗУБР").get("disc_diameter").number == Decimal("125")
    assert _ushm(rules, "Болгарка круг 230").get("disc_diameter").number == Decimal("230")


def test_ushm_no_load_speed_takes_max_in_range(rules):
    # «2800-11000 об/мин» → берём максимум 11000, не 2800.
    assert _ushm(rules, "УШМ 900Вт, 2800-11000 об/мин").get("no_load_speed").number == Decimal(
        "11000"
    )


def test_ushm_spindle_thread(rules):
    assert _ushm(rules, "УШМ Bosch GWS M14 125мм").get("spindle_thread").option_slug == "m14"
    assert _ushm(rules, "УШМ мини М10 76мм").get("spindle_thread").option_slug == "m10"
    assert "spindle_thread" not in _ushm(rules, "Шлифмаш угл Makita DGA504RF")


def test_ushm_cordless_attributes(rules):
    found = _ushm(rules, "Шлифмаш угл аккум STURM CAG18125BLE 18В, 125мм бесщеточная 1х4А/ч ЗУ")
    assert found["voltage"].number == Decimal("18")
    assert found["power_source"].option_slug == "battery"
    assert found["motor_type"].option_slug == "brushless"
    assert found["disc_diameter"].number == Decimal("125")


def test_ushm_power_not_confused_with_voltage(rules):
    # «1700Вт» — мощность, не напряжение.
    found = _ushm(rules, "Шлифмаш угл 1700Вт")
    assert found["power"].number == Decimal("1700")
    assert "voltage" not in found


@pytest.mark.django_db
def test_attribute_coverage_command_counts():
    """Команда attribute_coverage считает покрытие по товарам нужного tool_type."""
    tt_attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    option = AttributeOption.objects.create(attribute=tt_attr, value="Дрели и шуруповёрты", slug=TT)
    p = Product.objects.create(
        name="Дрель", original_name="Дрель аккумуляторная 18V 55 Нм бесщёточная без АКБ", slug="d-1"
    )
    ProductAttributeValue.objects.create(product=p, attribute=tt_attr, value_option=option)

    out = StringIO()
    call_command("attribute_coverage", "--tool-type", TT, stdout=out)
    report = out.getvalue()
    assert "товаров 1" in report
    assert "voltage" in report and "100%" in report
