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


def test_ushm_model_extraction_disc_and_power(rules):
    # Диаметр/мощность из кода модели «УШМ-<Ø>[-/]<Вт>», AG<Ø>-<Вт>.
    f1 = _ushm(rules, "Шлифмаш угл ИНТЕРСКОЛ УШМ-125/1100")
    assert f1["disc_diameter"].number == Decimal("125") and f1["power"].number == Decimal("1100")
    f2 = _ushm(rules, "Шлифмаш угл ЗУБР ПРОФ УШМ-П230-2000 П")
    assert f2["disc_diameter"].number == Decimal("230") and f2["power"].number == Decimal("2000")
    f3 = _ushm(rules, "Шлифмаш угл DENZEL AG125-1500")
    assert f3["disc_diameter"].number == Decimal("125") and f3["power"].number == Decimal("1500")
    f4 = _ushm(rules, "Шлифмаш угл AG230-2200")
    assert f4["disc_diameter"].number == Decimal("230") and f4["power"].number == Decimal("2200")


def test_ushm_model_extraction_guards(rules):
    # Напряжение АКБ в коде модели НЕ должно попасть в power (опасный кейс ревью).
    f1 = _ushm(rules, "Шлифмаш угл аккум AG125-18V")
    assert f1["disc_diameter"].number == Decimal("125") and "power" not in f1
    f2 = _ushm(rules, "Шлифмаш угл аккум. УШМ-125/18В, 1Х4,0Ач ИНТЕРСКОЛ")
    assert f2["disc_diameter"].number == Decimal("125") and "power" not in f2
    # Неканоничный код модели → ничего не извлекаем.
    f3 = _ushm(rules, "Шлифмаш угл ИНТЕРСКОЛ УШМ-2322ЭМ")
    assert "disc_diameter" not in f3 and "power" not in f3
    # AG как часть слова (Aggressor/AGCS) не должно ловиться как Ø.
    assert "disc_diameter" not in _ushm(rules, "Круг лепестковый Aggressor 125")


def test_power_source_inferred_mains_when_corded(rules):
    # Сетевая УШМ без слова «сетевой»: есть power, нет voltage/АКБ → инференс «Сеть».
    for name in ("Шлифмаш угл ИНТЕРСКОЛ УШМ-125/1100", "Шлифмаш угл DENZEL AG125-1500"):
        ps = _ushm(rules, name).get("power_source")
        assert ps is not None and ps.option_slug == "mains" and ps.source == "inferred"


def test_power_source_inference_skips_cordless(rules):
    # Аккумуляторная (есть voltage/АКБ) → инференс «Сеть» НЕ срабатывает.
    f1 = _ushm(rules, "Шлифмаш угл аккум DENZEL AG125-18V, 1х4.0Ач")
    assert f1["power_source"].option_slug == "battery" and f1["power_source"].source == "keyword"
    f2 = _ushm(rules, "Шлифмаш угл STURM CAG18125 18В, 125мм")
    assert f2.get("power_source") is None or f2["power_source"].option_slug != "mains"


def test_power_source_explicit_keyword_not_overridden(rules):
    # Явное «сетевой» → keyword mains (не inferred, без дубля).
    ps = _ushm(rules, "Шлифмаш угл сетевой ИНТЕРСКОЛ УШМ-125/1100").get("power_source")
    assert ps.option_slug == "mains" and ps.source == "keyword"


def test_power_source_inference_requires_power(rules):
    # Нет power (только Ø) → инференс молчит (requires_present не выполнен).
    assert _ushm(rules, "Шлифмаш угл 125мм").get("power_source") is None


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


LOBZIKI = "lobziki"


def _lobziki(rules: AttributeRules, name: str):
    return {v.slug: v for v in rules.extract(LOBZIKI, name)}


def test_lobziki_corded_full_name(rules):
    # Сетевой лобзик: power + stroke_rate, power_source инферится как «Сеть».
    f = _lobziki(rules, 'Лобзик Bosch GST 65B; "D"захват; 400Вт, 3100х/мин')
    assert f["power"].number == Decimal("400")
    assert f["stroke_rate"].number == Decimal("3100")
    assert f["power_source"].option_slug == "mains" and f["power_source"].source == "inferred"


def test_lobziki_stroke_rate_takes_value_at_unit_in_range(rules):
    # Диапазон «850-3000х/мин» → берётся число у «х/мин» (3000).
    assert _lobziki(rules, "Лобзик CJ120V; 740Вт, 850-3000х/мин")["stroke_rate"].number == Decimal(
        "3000"
    )


def test_lobziki_stroke_rate_space_and_hod_variants(rules):
    # Пробел перед «х/мин» и форма «ход/мин».
    assert _lobziki(rules, "Лобзик 3000 х/мин")["stroke_rate"].number == Decimal("3000")
    assert _lobziki(rules, "Лобзик 3000 ход/мин")["stroke_rate"].number == Decimal("3000")


def test_lobziki_stroke_rate_guard_rejects_other_units(rules):
    # «х/метр» не должно ловиться как частота ходов.
    assert "stroke_rate" not in _lobziki(rules, "Лобзик ход 3000 х/метр")


def test_lobziki_cordless_attributes(rules):
    # Аккумуляторный: voltage/ёмкость/частота; power_source = battery, НЕ инференс.
    f = _lobziki(rules, "Лобзик аккум CJ10DL; 10,8V,1,5А/ч,Li-ion,0-2700х/м")
    assert f["stroke_rate"].number == Decimal("2700")
    assert f["voltage"].number == Decimal("10.8")
    assert f["battery_capacity"].number == Decimal("1.5")
    assert f["power_source"].option_slug == "battery"


def test_lobziki_power_source_inferred_mains(rules):
    # Есть power, нет voltage/АКБ/battery_included → инференс «Сеть».
    assert _lobziki(rules, "Лобзик 600Вт 3000х/мин")["power_source"].option_slug == "mains"


def test_lobziki_power_source_inference_blocked_by_battery_included(rules):
    # Правка ревью: «без АКБ» (battery_included) без распознанного voltage НЕ должно
    # ошибочно стать mains — даже если есть power. battery_included в requires_absent.
    f = _lobziki(rules, "Лобзик 500Вт без АКБ 2700х/мин")
    assert "battery_included" in f and f["battery_included"].boolean is False
    assert f.get("power_source") is None or f["power_source"].option_slug != "mains"


# --- Алмазные круги (tool_type=krugi-almaznye) -------------------------------

ALMAZ = "krugi-almaznye"


def _almaz(rules: AttributeRules, name: str):
    return {v.slug: v for v in rules.extract(ALMAZ, name)}


def test_almaz_full_format_diameter_and_bore(rules):
    f = _almaz(rules, "Круг алмаз. отрез. 125х2,0х22,23 ЗУБР")
    assert f["disc_diameter"].number == Decimal("125")
    assert f["bore"].number == Decimal("22.23")


def test_almaz_bore_after_third_separator(rules):
    # Посадочный — после 3-го «х» в «125х1,2х10х22,23».
    f = _almaz(rules, "Круг алмаз. отрез. 125х1,2х10х22,23 SKYWER")
    assert f["disc_diameter"].number == Decimal("125")
    assert f["bore"].number == Decimal("22.23")


def test_almaz_diameter_bore_disc_type(rules):
    f1 = _almaz(rules, "Круг алмаз. отрез. 230х22,2 сплошной")
    assert f1["disc_diameter"].number == Decimal("230")
    assert f1["bore"].number == Decimal("22.2")
    assert f1["disc_type"].option_slug == "solid"
    f2 = _almaz(rules, "Круг алмаз отрез 350х25,4 сегмент")
    assert f2["disc_diameter"].number == Decimal("350")
    assert f2["bore"].number == Decimal("25.4")
    assert f2["disc_type"].option_slug == "segment"


def test_almaz_disc_type_turbo_wins_over_segment(rules):
    # «турбо-сегментный» → turbo (порядок вариантов turbo раньше segment).
    assert (
        _almaz(rules, "Круг алмазный турбо-сегментный 230х22,23")["disc_type"].option_slug
        == "turbo"
    )


def test_almaz_disc_type_latin_turbo(rules):
    # В названиях 1С массово латинское «Turbo/TURBO» — учитываем обе раскладки.
    assert (
        _almaz(rules, "Круг алмаз. отрез. 115х2,0х7х22,2 TURBO EXTRA")["disc_type"].option_slug
        == "turbo"
    )


def test_almaz_disc_type_1a1r_is_solid(rules):
    # Код формы 1A1R = сплошной обод (continuous rim) — самый частый маркер сплошных.
    assert (
        _almaz(rules, "Круг алмаз. отрез. 125х1,4х10х22,23 1A1R Сухорез")["disc_type"].option_slug
        == "solid"
    )
    # Турбо приоритетнее обода: «1A1R Turbo» → turbo (порядок вариантов).
    assert (
        _almaz(rules, "Круг алмаз. отрез. 115х1,1х10х22,23 1A1R Turbo SUPREME")[
            "disc_type"
        ].option_slug
        == "turbo"
    )


def test_almaz_bare_diameter_whitelist(rules):
    # «125 УНИВЕРСАЛ» без «х» — whitelist ловит Ø; посадочного/типа нет.
    f = _almaz(rules, "Круг алмаз. отрез. 125 УНИВЕРСАЛ ЗУБР")
    assert f["disc_diameter"].number == Decimal("125")
    assert "bore" not in f and "disc_type" not in f


def test_almaz_adapter_ring_extracts_nothing(rules):
    # Кольца-переходники не несут Ø из whitelist → ничего не извлекаем (важный негатив).
    assert _almaz(rules, "Кольцо переходное 22,2-20 мм для дисков") == {}
    assert "bore" not in _almaz(rules, "Кольцо переходное 30х22,2 для дисков")  # Ø-anchor


# --- Новые типы Электроинструмента (переиспользуют power/voltage/impact_energy + saw_type) ---


def test_shlifmashiny_power_and_source(rules):
    f = {
        v.slug: v
        for v in rules.extract("shlifmashiny", "Шлифмаш вибр Bosch GSS 23 AE, 190Вт, сетевая")
    }
    assert f["power"].number == Decimal("190")
    assert f["power_source"].option_slug == "mains"


def test_shlifmashiny_cordless_voltage(rules):
    f = {
        v.slug: v
        for v in rules.extract("shlifmashiny", "Шлифмаш эксцентрик аккум 18В Li-ion без АКБ")
    }
    assert f["voltage"].number == Decimal("18")
    assert f["power_source"].option_slug == "battery"
    assert f["battery_included"].boolean is False


def test_otboynye_molotki_power_and_impact(rules):
    f = {
        v.slug: v
        for v in rules.extract(
            "otboynye-molotki", "Молоток отб TE-DH 32. SDS-MAX ,1500Вт, 32Дж, 10,8 кг"
        )
    }
    assert f["power"].number == Decimal("1500")
    assert f["impact_energy"].number == Decimal("32")


def test_pily_saw_type(rules):
    def slug(name):
        return {v.slug: v for v in rules.extract("pily", name)}["saw_type"].option_slug

    assert slug("Пила дисковая аккум. Makita DSS610") == "diskovaya"
    assert slug("Пила сабельная аккум DENZEL CRC-115") == "sabelnaya"
    assert slug("Пила цепная электрическая 2000Вт") == "tsepnaya"


def test_frezery_power(rules):
    f = {v.slug: v for v in rules.extract("frezery", "Фрезер Einhell TC-RO 1155 E, 1100Вт, 55мм")}
    assert f["power"].number == Decimal("1100")


# --- Буры (tool_type=bury): Ø×длина + хвостовик SDS ---------------------------


def test_bury_diameter_length_shank_plus(rules):
    # «Бур 5х165х100» → Ø=5, длина=165 (по первому «х»), хвостовик SDS-plus.
    f = {v.slug: v for v in rules.extract("bury", "Бур 5х165х100 SDS+ Hitachi")}
    assert f["diameter"].number == Decimal("5")
    assert f["length"].number == Decimal("165")
    assert f["shank_type"].option_slug == "sds-plus"


def test_bury_sds_max_two_digit_diameter(rules):
    f = {v.slug: v for v in rules.extract("bury", "Бур SDS-max 18х450 Bosch")}
    assert f["diameter"].number == Decimal("18")
    assert f["length"].number == Decimal("450")
    assert f["shank_type"].option_slug == "sds-max"


# --- Коронки (tool_type=koronki): одиночный Ø + посадка + назначение ----------


def test_koronki_single_diameter_mount_purpose(rules):
    f = {v.slug: v for v in rules.extract("koronki", "Коронка 65 мм по бетону SDS+ СЕБ")}
    assert f["diameter"].number == Decimal("65")
    assert f["mount"].option_slug == "sds-plus"
    assert f["purpose"].option_slug == "beton"


def test_koronki_small_diamond_bit_m14(rules):
    # Алмазная коронка «6 мм М14» — одноцифровой Ø и посадка М14.
    f = {v.slug: v for v in rules.extract("koronki", "Коронка алм. 6 мм М14 ЗУБР керамогранит")}
    assert f["diameter"].number == Decimal("6")
    assert f["mount"].option_slug == "m14"


# --- Свёрла (tool_type=sverla): Ø + материал + назначение + хвостовик ----------


def test_sverla_metal_drill_full(rules):
    f = {v.slug: v for v in rules.extract("sverla", "Сверло по металлу ц/х 6,0 мм Р6М5 ГОСТ")}
    assert f["diameter"].number == Decimal("6.0")
    assert f["shank_type"].option_slug == "tsilindr"
    assert f["material"].option_slug == "hss"
    assert f["purpose"].option_slug == "metall"


def test_sverla_hex_shank_diameter_via_f(rules):
    f = {
        v.slug: v for v in rules.extract("sverla", "Сверло 6-гранное ф 4,0 мм Р4М3 нитридтитановое")
    }
    assert f["diameter"].number == Decimal("4.0")
    assert f["shank_type"].option_slug == "hex"


# --- Хвост Оснастки: Пики/долота, Биты, Пилки/полотна, Резцы -------------------


def test_piki_dolota_shank_and_length(rules):
    f = {v.slug: v for v in rules.extract("piki-dolota", "Долото 20х250 SDS-PLUS ЗУБР")}
    assert f["shank_type"].option_slug == "sds-plus"
    assert f["length"].number == Decimal("250")


def test_bity_bit_type(rules):
    def opt(name):
        return {v.slug: v for v in rules.extract("bity", name)}["bit_type"].option_slug

    assert opt("Бита PH2 25мм") == "ph"
    assert opt("Бита TX20 50мм") == "torx"
    assert opt("Бита PZ2 50мм ЗУБР") == "pz"


def test_pilki_purpose_and_saw_for(rules):
    f = {
        v.slug: v for v in rules.extract("pilki-polotna", "Пилки для электролобзика по металлу 2шт")
    }
    assert f["purpose"].option_slug == "metall"
    assert f["saw_for"].option_slug == "lobzik"


def test_reztsy_material(rules):
    f = {v.slug: v for v in rules.extract("reztsy", "Резец проходной 16х16 Т15К6 твердосплав")}
    assert f["material"].option_slug == "carbide"


# --- Шлифкруги (tool_type=krugi-shlif): Ø-whitelist + тип абразива --------------


def test_krugi_shlif_diameter_and_type(rules):
    f = {v.slug: v for v in rules.extract("krugi-shlif", "Круг лепестковый КЛТ 125х22,2 P60 ЗУБР")}
    assert f["disc_diameter"].number == Decimal("125")
    assert f["disc_type"].option_slug == "flap"


def test_krugi_shlif_grinding_type(rules):
    f = {v.slug: v for v in rules.extract("krugi-shlif", "Круг шлифовальный 150х20х32 14А")}
    assert f["disc_diameter"].number == Decimal("150")
    assert f["disc_type"].option_slug == "grinding"


# --- Ручной инструмент: ключи / отвёртки / головки / воротки / молотки ---------


def test_klyuchi_type_and_size(rules):
    f = {v.slug: v for v in rules.extract("klyuchi-gaechnye", "Ключ комбинированный 17мм CrV ЗУБР")}
    assert f["wrench_type"].option_slug == "kombinir"
    assert f["size"].number == Decimal("17")


def test_golovki_drive_and_size(rules):
    f = {v.slug: v for v in rules.extract("golovki", 'Головка торцевая 1/2" 13мм 6-гранная')}
    assert f["drive"].option_slug == "d-1-2"
    assert f["size"].number == Decimal("13")


def test_vorotki_drive_and_type(rules):
    f = {v.slug: v for v in rules.extract("vorotki", "Вороток 1/2 250мм Т-образный с трещоткой")}
    assert f["drive"].option_slug == "d-1-2"
    assert f["vorotok_type"].option_slug == "treshch"  # трещотка приоритетнее


def test_molotki_weight_and_type(rules):
    f = {v.slug: v for v in rules.extract("molotki", "Молоток слесарный 500г фиберглас")}
    assert f["weight"].number == Decimal("500")
    assert f["molotok_type"].option_slug == "slesar"


def test_otvertki_bit_profile(rules):
    f = {v.slug: v for v in rules.extract("otvertki", "Отвертка крестовая PH2x100мм")}
    assert f["bit_type"].option_slug == "ph"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Набор отверток 10шт KRAFTOOL X-DRIVE", 10),
        ("Набор отвертка 6 предметов Ultra Grip", 6),
        ("Набор отверток 34 предмета ЗУБР Компакт", 34),
        ("Набор отверток KRAFTOOL 19в1", 19),
        ("Отвертка с набором бит 145 предметов Cablexpert", 145),
    ],
)
def test_nabory_otvertok_piece_count(rules, name, expected):
    v = {x.slug: x for x in rules.extract("nabory-otvertok", name)}.get("piece_count")
    assert v is not None and v.number == Decimal(str(expected))


def test_nabory_otvertok_piece_count_ignores_model_codes(rules):
    # Модельный код без «шт/предметов» (латиница не транслитерируется) не даёт ложного piece_count.
    f = {x.slug: x for x in rules.extract("nabory-otvertok", "Набор отверток SD-9302 ProsKit")}
    assert "piece_count" not in f


# --- Метчики / Плашки (tool_type=metchiki/plashki): Ø + шаг + тип резьбы + материал ---


def test_metchiki_metric_full(rules):
    # Метрический винтовой: Ø + шаг из «М 6х1,0», материал HSS, тип резьбы выведен (derive).
    f = {v.slug: v for v in rules.extract("metchiki", "Метчик винтовой М 6х1,0 HSS STV")}
    assert f["diameter"].number == Decimal("6")
    assert f["thread_pitch"].number == Decimal("1.0")
    assert f["material"].option_slug == "hss"
    # «Метрическая» выводится из наличия diameter, источник — inferred.
    assert f["thread_type"].option_slug == "metric"
    assert f["thread_type"].source == "inferred"


def test_metchiki_metric_keyword_din(rules):
    # DIN371 — keyword-метрическая (не derive); шаг с дробью; р6м5к5 → HSS.
    f = {v.slug: v for v in rules.extract("metchiki", "Метчик М 8х1,25 DIN371 р6м5к5")}
    assert f["diameter"].number == Decimal("8")
    assert f["thread_pitch"].number == Decimal("1.25")
    assert f["thread_type"].option_slug == "metric"
    assert f["thread_type"].source == "keyword"
    assert f["material"].option_slug == "hss"


def test_metchiki_machine_hand_format(rules):
    # Машинно-ручной «м/р 10х1,5» (без префикса М) — Ø/шаг ловятся вторым паттерном; 9ХС → легированная.
    f = {v.slug: v for v in rules.extract("metchiki", "Метчик м/р 10х1,5 9ХС")}
    assert f["diameter"].number == Decimal("10")
    assert f["thread_pitch"].number == Decimal("1.5")
    assert f["material"].option_slug == "alloy"


def test_plashki_inch_thread(rules):
    # Дюймовая резьба по ключам UNF/ниток; метрического Ø нет.
    f = {v.slug: v for v in rules.extract("plashki", 'Плашка 9/16" UNF 18 ниток STV')}
    assert f["thread_type"].option_slug == "inch"
    assert "diameter" not in f


def test_plashki_pipe_thread(rules):
    f = {v.slug: v for v in rules.extract("plashki", "Плашка G 1/2 трубная")}
    assert f["thread_type"].option_slug == "pipe"


def test_metchiki_inch_has_no_metric_diameter(rules):
    # Дюймовый BSW не должен получить ложный метрический Ø/шаг.
    f = {v.slug: v for v in rules.extract("metchiki", "Метчик дюймовый BSW 1/2 12ниток к-т 2шт")}
    assert "diameter" not in f
    assert f["thread_type"].option_slug == "inch"


# --- Измерительный: рулетки (длина/ширина ленты) и уровни (длина) -----------------


def test_izm_ruletki_length_and_width(rules):
    f = {
        v.slug: v
        for v in rules.extract("izm-ruletki", "Рулетка 10 м (25 мм) с тройным стопом Inforce")
    }
    assert f["tape_length"].number == Decimal("10")
    assert f["tape_width"].number == Decimal("25")


def test_izm_ruletki_width_not_taken_as_length(rules):
    # Ширина «(19мм)» не должна попасть в длину; длина — «5м».
    f = {v.slug: v for v in rules.extract("izm-ruletki", "Рулетка 5м (19мм) STAYER")}
    assert f["tape_length"].number == Decimal("5")
    assert f["tape_width"].number == Decimal("19")


def test_izm_ruletki_length_only(rules):
    f = {v.slug: v for v in rules.extract("izm-ruletki", "Рулетка 3 м Hitachi")}
    assert f["tape_length"].number == Decimal("3")
    assert "tape_width" not in f


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Уровень 600мм ЗУБР КОМПАКТ", 600),
        ("Уровень 2000 мм PROFI", 2000),
        ("Уровень 400 мм магнитный", 400),
    ],
)
def test_izm_urovni_length(rules, name, expected):
    f = {v.slug: v for v in rules.extract("izm-urovni", name)}
    assert f["length"].number == Decimal(str(expected))


# --- Измерительный: штангенциркули (диапазон + тип отсчёта) и дальномеры (дальность) ---


def test_izm_shtangen_digital(rules):
    # Диапазон — первый «мм» (150), точность «0,02мм» не утекает; «электронный» → digital.
    f = {
        v.slug: v for v in rules.extract("izm-shtangen", "Штангенциркуль 150 мм 0,02мм электронный")
    }
    assert f["measuring_range"].number == Decimal("150")
    assert f["readout_type"].option_slug == "digital"


def test_izm_shtangen_vernier_default(rules):
    # Без «электронный/циферблат» механический штангенциркуль → нониусный (фолбэк по слову).
    f = {
        v.slug: v for v in rules.extract("izm-shtangen", "Штангенциркуль 125мм тип 1 металлический")
    }
    assert f["measuring_range"].number == Decimal("125")
    assert f["readout_type"].option_slug == "vernier"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Дальномер лаз. Bosch GLM 30; диап. изм.0,15-30м", 30),
        ("Дальномер лазерный ADA до 100м", 100),
    ],
)
def test_izm_dalnomery_max_distance(rules, name, expected):
    f = {v.slug: v for v in rules.extract("izm-dalnomery", name)}
    assert f["max_distance"].number == Decimal(str(expected))


# --- Измерительный: угольники (размер) и микрометры (диапазон из пары A-B) ---------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Угольник 250 мм Startul", 250),
        ("Угольник 160х100 УП-1-160 Буревестник", 160),
        ("Угольник кровельный 170мм высокоточный KRAFTOOL", 170),
    ],
)
def test_izm_ugolniki_size(rules, name, expected):
    f = {v.slug: v for v in rules.extract("izm-ugolniki", name)}
    assert f["size"].number == Decimal(str(expected))


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Микрометр МК-100 75-100/0,01 мм", 100),
        ("Микрометр МК-0-25 0,01", 25),
        ("Микрометр МК-150-200 0,01мм индикаторный", 200),
    ],
)
def test_izm_mikrometry_range(rules, name, expected):
    # Диапазон — верхняя граница пары «A-B» (0-25 → 25, 75-100 → 100).
    f = {v.slug: v for v in rules.extract("izm-mikrometry", name)}
    assert f["measuring_range"].number == Decimal(str(expected))


def test_izm_niveliry_type(rules):
    laser = {v.slug: v for v in rules.extract("izm-niveliry", "Нивелир лазерный Bosch GLL 2-10")}
    assert laser["level_type"].option_slug == "laser"
    opt = {v.slug: v for v in rules.extract("izm-niveliry", "Нивелир оптический ADA RUNNER 24")}
    assert opt["level_type"].option_slug == "optical"


def _attrs(rules, tt, name):
    return {v.slug: v for v in rules.extract(tt, name)}


@pytest.mark.parametrize(
    "name,length,ptype",
    [
        ("Длинногубцы 160 мм прямые Matrix", 160, "dlinnogubtsy"),
        ("Пассатижи 200мм ЗУБР", 200, "passatizhi-t"),
        ("Утконосы 250 мм Matrix", 250, "utkonosy"),
        ("Круглогубцы 140 мм", 140, "kruglogubtsy"),
    ],
)
def test_passatizhi_length_and_type(rules, name, length, ptype):
    f = _attrs(rules, "passatizhi", name)
    assert f["length"].number == Decimal(str(length))
    assert f["plier_type"].option_slug == ptype


@pytest.mark.parametrize(
    "name,length,btype",
    [
        ("Бокорезы 110 мм МИНИ Archimedes", 110, "bokorezy-t"),
        ("Кусачки боковые 160мм KRAFTOOL", 160, "kusachki"),
        ("Клещи переставные 250мм Hanskonner", 250, "kleshchi"),
    ],
)
def test_bokorezy_length_and_type(rules, name, length, btype):
    f = _attrs(rules, "bokorezy", name)
    assert f["length"].number == Decimal(str(length))
    assert f["bokorez_type"].option_slug == btype


@pytest.mark.parametrize(
    "name,cap,dtype",
    [
        ("Домкрат бутылочный 2т 150-310мм ЗУБР", "2", "butylochnyy"),
        ("Домкрат 1,5т ромбовый 110-360мм Stels", "1.5", "rombovyy"),
        ("Домкрат подкатной гидравлический 3т Inforce", "3", "gidravl"),
        ("Домкрат реечный 5 т", "5", "reechnyy"),
    ],
)
def test_domkraty_capacity_and_type(rules, name, cap, dtype):
    f = _attrs(rules, "domkraty", name)
    assert f["capacity"].number == Decimal(cap)
    assert f["domkrat_type"].option_slug == dtype


def test_domkraty_capacity_ignores_cyrillic_after_t(rules):
    # «т» внутри слова (телескопический/тонна без цифры) не должно давать ложную тоннаж.
    f = _attrs(rules, "domkraty", "Домкрат телескопический подкатной")
    assert "capacity" not in f


@pytest.mark.parametrize(
    "name,length,saw_for",
    [
        ("Ножовка по дереву 450мм Бобер", 450, "po-derevu"),
        ("Ножовка по металлу 300 мм STAYER", 300, "po-metallu"),
        ("Ножовка для газобетона 700мм", 700, "po-gazobetonu"),
    ],
)
def test_nozhovki_length_and_purpose(rules, name, length, saw_for):
    f = _attrs(rules, "nozhovki", name)
    assert f["length"].number == Decimal(str(length))
    assert f["nozhovka_for"].option_slug == saw_for


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
