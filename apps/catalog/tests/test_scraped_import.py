"""Тесты импортёра спарсенных характеристик (PARS-04).

Ключевые гарантии: матчинг без подстрочного сравнения, неоднозначность — в отчёт
(не в базу), ``--dry-run`` без единой записи, идемпотентность, приоритеты
источников (scraper > regex, scraper < import_1c/manual), voltage — только
аккумуляторным.
"""

import json
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog import scraped_import as si
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    ImportRun,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)

ATTRS = {
    "tool_type": (AttributeType.SELECT, ""),
    "power": (AttributeType.DECIMAL, "Вт"),
    "voltage": (AttributeType.DECIMAL, "В"),
    "energy_impact": (AttributeType.DECIMAL, "Дж"),
    "no_load_speed": (AttributeType.DECIMAL, "об/мин"),
    "chuck": (AttributeType.SELECT, ""),
    "motor_type": (AttributeType.SELECT, ""),
    "power_source": (AttributeType.SELECT, ""),
}
OPTIONS = {
    "tool_type": [("perforatory", "Перфораторы")],
    "chuck": [("sds-plus", "SDS-plus"), ("sds-max", "SDS-max")],
    "motor_type": [("brushed", "Щёточный"), ("brushless", "Бесщёточный")],
    "power_source": [("mains", "Сеть"), ("battery", "Аккумулятор")],
}


@pytest.fixture
def catalog(db):
    cat = Category.add_root(name="Перфораторы", slug="perf")
    attrs = {}
    for slug, (atype, unit) in ATTRS.items():
        attrs[slug] = Attribute.objects.create(
            slug=slug, name=slug, attribute_type=atype, unit=unit
        )
    opts = {}
    for slug, values in OPTIONS.items():
        for oslug, value in values:
            opts[(slug, oslug)] = AttributeOption.objects.create(
                attribute=attrs[slug], value=value, slug=oslug
            )
    return {"category": cat, "attrs": attrs, "opts": opts}


def _product(catalog, name, **kw):
    defaults = dict(
        category=catalog["category"],
        name=name,
        slug=f"p{Product.objects.count()}",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    defaults.update(kw)
    p = Product.objects.create(**defaults)
    ProductAttributeValue.objects.create(
        product=p,
        attribute=catalog["attrs"]["tool_type"],
        value_option=catalog["opts"][("tool_type", "perforatory")],
        source=Source.RULES,
    )
    return p


def _pav(catalog, product, slug, source, decimal=None, option=None):
    return ProductAttributeValue.objects.create(
        product=product,
        attribute=catalog["attrs"][slug],
        value_decimal=decimal,
        value_option=catalog["opts"].get((slug, option)) if option else None,
        source=source,
    )


def _export(tmp_path, cards, source="zubr"):
    path = tmp_path / f"{source}.products.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source": source,
                "created_at": "2026-07-28T00:00:00Z",
                "category": {"name": "Перфораторы", "source_url": "https://zubr.ru/x/"},
                "products": cards,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(path)


def _zubr_card(name, sku, power="1000"):
    return {
        "source_url": "https://zubr.ru/x/?ID=1",
        "name": name,
        "brand": None,
        "manufacturer_sku": sku,
        "description": None,
        "summary_raw": None,
        "attributes": {
            "Мощность, Вт": power,
            "Максимальная энергия удара, Дж": "3.2",
            "Напряжение питания, В/Гц": "230/50",
            "Патрон": "SDS Plus",
            "Реверс": "щеточный",  # мусор источника — ignore в карте
            "Частота вращения шпинделя, об/мин": "0-1200",
        },
    }


def _card(name, sku):
    return {"name": name, "brand": None, "manufacturer_sku": sku}


def _run(export_path, *extra):
    call_command(
        "catalog_import_scraped",
        export_path,
        "--category",
        "perforatory",
        *extra,
        verbosity=0,
    )


def _run_report(tmp_path, export_path, *extra):
    report_path = tmp_path / "report.json"
    _run(export_path, "--report", str(report_path), *extra)
    return json.loads(report_path.read_text(encoding="utf-8"))


# --- матчинг (unit) -----------------------------------------------------------


def test_model_key_no_substring_trap():
    """Ловушка Phase 1: ЗП-2680 — подстрока ключа ЗП-26-800. Равенства нет."""
    assert si.model_key("Перф.ЗУБР ЗП-2680, SDS+") == "zp2680"
    assert si.model_key("Перф.ЗУБР ЗП-26-800 SDS+") == "zp26800"
    assert si.model_key("Перф.ЗУБР ЗП-2680, SDS+") != si.model_key("Перф.ЗУБР ЗП-26-800 SDS+")


def test_model_re_zdm_prefix():
    """ПАРС-09: префикс ЗДМ (дрели-миксеры ЗУБР) извлекается из названия карточки."""
    assert si.extract_model("Дрель-миксер ЗДМ-820 РМ") == "ЗДМ-820 РМ"
    assert si.extract_model("Дрель-миксер ЗДМ-1200 РММ2") == "ЗДМ-1200 РММ2"
    assert si.model_key("Дрель-миксер ЗДМ-820 РМ") == "zdm820rm"
    assert si.model_key("Дрель-миксер ЗДМ-1200 РММ2") == "zdm1200rmm2"
    # РММ2 и РММ — разные модификации, ключи не склеиваются.
    assert si.model_key("Дрель-миксер ЗДМ-1200 РММ2") != si.model_key("Дрель-миксер ЗДМ-1200 РММ")


def test_model_re_zdm_card_and_product_keys_equal():
    """Карточка и товар каталога дают один ключ модели (карточка ЗДМ-820 РМ)."""
    card_key = si.model_key("Дрель-миксер ЗДМ-820 РМ")
    product_key = si.model_key(
        "Дрель-миксер реверсивная ЗУБР ЗДМ-820 РМ Профессионал, 50 Нм, "
        "патрон 13 мм, 0-650 об/мин, 820 Вт"
    )
    assert card_key == product_key


@pytest.mark.django_db
def test_substring_match_impossible(catalog):
    """Карточка ЗП-26-800 НЕ матчится с товаром ЗП-2680 (и наоборот)."""
    p = _product(catalog, "Перф.ЗУБР ЗП-2680, SDS+, реверс, 850Вт")
    index = si.build_product_index(list(Product.objects.all()))
    card = {"name": "Перфоратор ЗУБР ЗП-26-800 К", "brand": None}
    m = si.match_card(card, "zubr", index)
    assert m.status == "not_found"
    card2 = {"name": "Перфоратор ЗУБР ЗП-2680", "brand": None}
    m2 = si.match_card(card2, "zubr", index)
    assert m2.status == "matched" and m2.products == [p]


@pytest.mark.django_db
def test_ambiguous_many_to_one_not_written(catalog, tmp_path):
    """Два товара с одним ключом модели → ambiguous, в базу ничего не пишется."""
    _product(catalog, "Перф. ВИХРЬ П-1000к")
    _product(catalog, "Перфоратор П-1000К Вихрь")
    card = _zubr_card("Перфоратор Вихрь П-1000К", "72/3/7")
    export = _export(tmp_path, [card], source="vihr")
    pav_before = ProductAttributeValue.objects.count()
    _run(export)
    assert ProductAttributeValue.objects.count() == pav_before


@pytest.mark.django_db
def test_many_cards_to_one_product_not_written(catalog, tmp_path):
    """Две карточки (П-24/700ЭР и П-24/700ЭР-2) → один товар: в отчёт, не в базу."""
    _product(catalog, "Перф. ИНТЕРСКОЛ П-24/700ЭР (кейс)")
    card1 = _zubr_card("П-24/700ЭР", "160.1.0.00")
    card2 = _zubr_card("П-24/700ЭР-2 Interskol", "977.1.0.70")
    export = _export(tmp_path, [card1, card2], source="interskol")
    pav_before = ProductAttributeValue.objects.count()
    _run(export)
    assert ProductAttributeValue.objects.count() == pav_before


# --- лестница матчинга (CODE-04) ---------------------------------------------


@pytest.mark.django_db
def test_sku_match_wins_over_model_collision(catalog):
    """Точный артикул/SKU разрешает коллизию, даже если модель совпадает."""
    p1 = _product(catalog, "Перф.ЗУБР ДА-24-2ЛК", article="SKU-123")
    _p2 = _product(catalog, "Перф.ЗУБР ДА-24-2ЛК/Б", article="SKU-456")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(_card("Перфоратор ЗУБР ДА-24-2ЛК", "SKU-123"), "zubr", index)
    assert m.status == "matched"
    assert m.products == [p1]
    assert m.matched_by == "sku"


@pytest.mark.django_db
def test_sku_match_without_model_in_card_name(catalog):
    """ПАРС-16: артикул проверяется ДО раннего выхода по нераспознанной модели.

    У карточки в имени нет ничего, что ловит ``MODEL_RE`` (термопистолет, пушка,
    насос — вся неинструментальная номенклатура), но артикул источника есть и
    совпадает с товаром. До правки функция выходила в ``not_found``, не дойдя до
    артикульной ветки.
    """
    card = _card("Термопистолет клеевой ЗУБР Профессионал", "ЗУБР-12345")
    assert si.extract_model(card["name"]) is None  # предпосылка теста
    p = _product(catalog, "Термопистолет клеевой ЗУБР", article="ЗУБР-12345")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(card, "zubr", index)
    assert m.status == "matched"
    assert m.products == [p]
    assert m.matched_by == "sku"


@pytest.mark.django_db
def test_no_model_and_no_sku_match_stays_not_found(catalog):
    """Без модели и без совпадения по артикулу вердикт остаётся ``not_found``."""
    _product(catalog, "Термопистолет клеевой ЗУБР", article="ЗУБР-12345")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(_card("Пила цепная ЗУБР", "ЗУБР-99999"), "zubr", index)
    assert m.status == "not_found"
    assert m.products == []


@pytest.mark.django_db
def test_sku_step_still_first_in_ladder(catalog):
    """Порядок лестницы не изменился: артикул выигрывает у точной модели."""
    p_sku = _product(catalog, "Термопистолет клеевой ЗУБР", article="SKU-777")
    _p_model = _product(catalog, "Перф.ЗУБР ЗП-26-800", article="SKU-778")
    index = si.build_product_index(list(Product.objects.all()))
    # в имени карточки есть модель ЗП-26-800 (ветка exact сработала бы),
    # но артикул указывает на другой товар — побеждает артикул.
    m = si.match_card(_card("Перфоратор ЗУБР ЗП-26-800", "SKU-777"), "zubr", index)
    assert m.status == "matched"
    assert m.products == [p_sku]
    assert m.matched_by == "sku"


@pytest.mark.django_db
def test_exact_model_wins_over_normalized(catalog):
    """Точная модель выигрывает у нормализованной, когда ключи совпадают."""
    p1 = _product(catalog, "Перф.ЗУБР ЗП-26-800", article="A")
    _p2 = _product(catalog, "Перф.ЗУБР ЗП-26800", article="B")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(_card("Перфоратор ЗУБР ЗП-26-800", "X"), "zubr", index)
    assert m.status == "matched"
    assert m.products == [p1]
    assert m.matched_by == "exact_model"


@pytest.mark.django_db
def test_normalized_model_wins_over_alias(catalog):
    """Нормализованная модель выигрывает у алиаса, когда точная модель не совпала."""
    _product(catalog, "Перф.ЗУБР ДА-24-2ЛК", article="A")
    p_suffix = _product(catalog, "Перф.ЗУБР ДА-24-2ЛК-У", article="B")
    index = si.build_product_index(list(Product.objects.all()))
    # у товара суффикс через дефис, у карточки слитно: exact не совпадает,
    # нормализованный ключ совпадает с суффиксным товаром, алиас — с базовым.
    m = si.match_card(_card("Перфоратор ЗУБР ДА-24-2ЛКУ", "X"), "zubr", index)
    assert m.status == "matched"
    assert m.products == [p_suffix]
    assert m.matched_by == "normalized_model"


@pytest.mark.django_db
def test_alias_match_last_ladder(catalog):
    """Алиас срабатывает последним, когда нет точного/нормализованного совпадения."""
    p_base = _product(catalog, "Перф.ЗУБР ДА-24-2ЛК", article="A")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(_card("Перфоратор ЗУБР ДА-24-2ЛК-У", "X"), "zubr", index)
    assert m.status == "matched"
    assert m.products == [p_base]
    assert m.matched_by == "alias"


@pytest.mark.django_db
def test_sku_multiple_products_same_article_is_ambiguous(catalog):
    """SKU без единственного товара — неоднозначность, не угадывание."""
    _product(catalog, "Перф.ЗУБР ДА-24-2ЛК", article="SKU-1")
    _product(catalog, "Перф.ЗУБР ДА-24-2ЛК/Б", article="SKU-1")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(_card("Перфоратор ЗУБР ДА-24-2ЛК", "SKU-1"), "zubr", index)
    assert m.status == "ambiguous"


@pytest.mark.django_db
def test_alias_yields_ambiguous_when_multiple_bases(catalog):
    """Алиас, который подходит к нескольким товарам, остаётся ambiguous."""
    _product(catalog, "Перф.ЗУБР ДА-24-2ЛК", article="A")
    _product(catalog, "Перф.ЗУБР ДА-24-2ЛК-Б", article="B")
    index = si.build_product_index(list(Product.objects.all()))
    m = si.match_card(_card("Перфоратор ЗУБР ДА-24-2ЛК-У", "X"), "zubr", index)
    assert m.status == "ambiguous"


@pytest.mark.django_db
def test_exact_card_kept_when_alias_card_collides(catalog, tmp_path):
    """Точная карточка остаётся matched, суффиксная уходит в ambiguous (CODE-04)."""
    _product(catalog, "Перф.ЗУБР ДА-24-2ЛК")
    card_exact = _zubr_card("Перфоратор ЗУБР ДА-24-2ЛК", "SKU-1")
    card_alias = _zubr_card("Перфоратор ЗУБР ДА-24-2ЛК-У", "SKU-2")
    export = _export(tmp_path, [card_exact, card_alias])
    report = _run_report(tmp_path, export)
    assert report["stats"]["matched"] == 1
    assert report["stats"]["ambiguous"] == 1
    assert len(report["matched"]) == 1
    assert report["matched"][0]["card"] == card_exact["name"]


# --- запись / приоритеты / voltage / конфликты --------------------------------


@pytest.mark.django_db
def test_write_creates_and_voltage_skipped_for_mains(catalog, tmp_path):
    p = _product(catalog, "Перф.ЗУБР ЗП-99-1000 К, SDS+")
    export = _export(tmp_path, [_zubr_card("Перфоратор ЗУБР ЗП-99-1000 К", "ЗП-99-1000 К")])
    _run(export)
    pavs = {pav.attribute.slug: pav for pav in p.attribute_values.all()}
    assert pavs["power"].value_decimal == Decimal("1000")
    assert pavs["power"].source == Source.SCRAPER
    assert pavs["energy_impact"].value_decimal == Decimal("3.2")
    assert pavs["chuck"].value_option.slug == "sds-plus"
    assert pavs["no_load_speed"].value_decimal == Decimal("1200")  # верхняя граница
    assert pavs["power_source"].value_option.slug == "mains"
    assert "voltage" not in pavs  # сетевой инструмент — voltage не пишется
    # мусорный «Реверс: щеточный» не стал motor_type
    assert "motor_type" not in pavs
    # attrs_cache пересобран точечно и совпадает с EAV
    p.refresh_from_db()
    assert p.attrs_cache["power"] is not None


@pytest.mark.django_db
def test_voltage_written_for_battery(catalog, tmp_path):
    p = _product(catalog, "Перф. аккум. ЗУБР ЗП-99-260 18В")
    card = _zubr_card("Перфоратор ЗУБР ЗП-99-260", "ЗП-99-260")
    card["attributes"]["Напряжение питания, В/Гц"] = "18"
    export = _export(tmp_path, [card])
    _run(export)
    pavs = {pav.attribute.slug: pav for pav in p.attribute_values.all()}
    assert pavs["voltage"].value_decimal == Decimal("18")  # < 60 В — аккумуляторный


@pytest.mark.django_db
def test_scraper_does_not_overwrite_any_source(catalog, tmp_path):
    """Автоматический overwrite запрещён: расхождения уходят в conflict, БД не меняется."""
    p_regex = _product(catalog, "Перф.ЗУБР ЗП-99-1000 К")
    _pav(catalog, p_regex, "power", Source.REGEX, decimal=Decimal("950"))
    p_1c = _product(catalog, "Перф.ЗУБР ЗП-98-1000 К")
    _pav(catalog, p_1c, "power", Source.IMPORT_1C, decimal=Decimal("900"))
    p_manual = _product(catalog, "Перф.ЗУБР ЗП-97-1000 К")
    _pav(catalog, p_manual, "power", Source.MANUAL, decimal=Decimal("800"))
    cards = [
        _zubr_card("Перфоратор ЗУБР ЗП-99-1000 К", "ЗП-99-1000 К"),
        _zubr_card("Перфоратор ЗУБР ЗП-98-1000 К", "ЗП-98-1000 К"),
        _zubr_card("Перфоратор ЗУБР ЗП-97-1000 К", "ЗП-97-1000 К"),
    ]
    export = _export(tmp_path, cards)
    report = _run_report(tmp_path, export)
    assert ProductAttributeValue.objects.get(
        product=p_regex, attribute__slug="power"
    ).value_decimal == Decimal("950")
    assert ProductAttributeValue.objects.get(
        product=p_1c, attribute__slug="power"
    ).value_decimal == Decimal("900")
    assert ProductAttributeValue.objects.get(
        product=p_manual, attribute__slug="power"
    ).value_decimal == Decimal("800")
    assert report["stats"]["conflict"] == 3
    assert report["stats"].get("overwrite", 0) == 0
    assert len(report["conflicts"]) == 3


@pytest.mark.django_db
def test_same_value_is_confirmed_not_conflict(catalog, tmp_path):
    """Совпадение значения — confirm, не конфликт."""
    p = _product(catalog, "Перф.ЗУБР ЗП-99-1000 К")
    _pav(catalog, p, "power", Source.MANUAL, decimal=Decimal("1000"))
    export = _export(tmp_path, [_zubr_card("Перфоратор ЗУБР ЗП-99-1000 К", "ЗП-99-1000 К")])
    report = _run_report(tmp_path, export)
    assert report["stats"]["confirm"] == 1
    assert report["stats"].get("conflict", 0) == 0


@pytest.mark.django_db
def test_dry_run_writes_nothing(catalog, tmp_path):
    _product(catalog, "Перф.ЗУБР ЗП-99-1000 К")
    export = _export(tmp_path, [_zubr_card("Перфоратор ЗУБР ЗП-99-1000 К", "ЗП-99-1000 К")])
    pav_before = ProductAttributeValue.objects.count()
    runs_before = ImportRun.objects.count()
    cache_before = list(Product.objects.values_list("id", "attrs_cache"))
    _run(export, "--dry-run")
    assert ProductAttributeValue.objects.count() == pav_before
    assert ImportRun.objects.count() == runs_before
    assert list(Product.objects.values_list("id", "attrs_cache")) == cache_before


@pytest.mark.django_db
def test_idempotent_second_run(catalog, tmp_path):
    p = _product(catalog, "Перф.ЗУБР ЗП-99-1000 К")
    export = _export(tmp_path, [_zubr_card("Перфоратор ЗУБР ЗП-99-1000 К", "ЗП-99-1000 К")])
    _run(export)
    pav_before = list(
        ProductAttributeValue.objects.order_by("id").values_list(
            "id", "attribute__slug", "value_decimal", "source"
        )
    )
    cache_before = Product.objects.get(id=p.id).attrs_cache
    _run(export)  # второй прогон — только confirm, без записей
    assert (
        list(
            ProductAttributeValue.objects.order_by("id").values_list(
                "id", "attribute__slug", "value_decimal", "source"
            )
        )
        == pav_before
    )
    assert Product.objects.get(id=p.id).attrs_cache == cache_before


# --- префиксы моделей из карты категории (PARS-13) ----------------------------


SHLIFMASHINY_PREFIXES = ["ЗЛШМ", "ЗОШМ", "ЗПШМ", "ВШМ", "ЛШМ", "ПШМ", "ЭШМ"]


def test_build_model_re_from_prefixes():
    """Регекс собирается из префиксов карты и извлекает шлифмашинную модель."""
    assert (
        si.extract_model("Лентошлифмашина ЛШМ-75/800", prefixes=SHLIFMASHINY_PREFIXES)
        == "ЛШМ-75/800"
    )
    assert si.model_key("Лентошлифмашина ЛШМ-75/800", prefixes=SHLIFMASHINY_PREFIXES) == "lshm75800"


def test_prefix_order_long_before_short():
    """Длинный префикс идёт раньше короткого: ЗПШМ > ПШМ."""
    prefixes = ["ПШМ", "ЗПШМ"]
    assert si.extract_model("Плоскошлифмашина ЗПШМ-300Е", prefixes=prefixes) == "ЗПШМ-300Е"


def test_fallback_without_model_prefixes_matches_legacy():
    """Без model_prefixes поведение совпадает с унаследованным MODEL_RE."""
    assert si.model_key("Перф.ЗУБР ЗП-26-800 SDS+") == "zp26800"
    assert si.model_key("Дрель-миксер ЗДМ-820 РМ") == "zdm820rm"


def test_validate_model_prefixes_rejects_regex_metacharacters():
    """Карта не может содержать regex-метасимволы в префиксах.

    Единственное исключение — унаследованный generic ``D[A-Z]{1,2}``.
    """
    with pytest.raises(ValueError, match="regex-метасимволы"):
        si.validate_model_prefixes(["ЗПШМ", "Z[A-Z]+"])
    # литеральные префиксы проходят
    si.validate_model_prefixes(["ЗЛШМ", "ПШМ", "DCG405"])
    # унаследованный generic разрешён
    si.validate_model_prefixes(si.LEGACY_MODEL_PREFIXES)
