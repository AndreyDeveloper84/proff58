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


# --- покрытие индекса каталога (ПАРС-17) --------------------------------------


@pytest.mark.django_db
def test_manufacturer_sku_from_product_name_feeds_sku_step(catalog):
    """Артикул производителя стоит в названии, поле ``article`` пустое.

    Так выглядит номенклатура Ресанты/Вихря в 1С («Перф. П-800к 72/3/6 ВИХРЬ»):
    до правки такой товар терял ступень SKU целиком.
    """
    p = _product(catalog, "Перф. П-800к 72/3/6 ВИХРЬ", article="")
    index = si.build_product_index(list(Product.objects.all()))
    assert index.entries[0].article_keys == ["7236"]
    m = si.match_card(_card("Перфоратор Вихрь П-800К", "72/3/6"), "vihr", index)
    assert m.status == "matched"
    assert m.products == [p]
    assert m.matched_by == "sku"


@pytest.mark.django_db
def test_garbage_rsv_article_not_indexed(catalog):
    """Мусорный ``РСВ-…`` не уникален: индекс игнорирует его, как ``article_check``.

    Иначе два товара с одним и тем же ``РСВ`` дают ``ambiguous`` на ровном месте,
    а настоящий артикул из названия остаётся рабочим.
    """
    p1 = _product(catalog, "Перф. П-1200к-м 72/3/3 ВИХРЬ", article="РСВ-140807")
    _p2 = _product(catalog, "Перф. П-900к-в 72/3/2 ВИХРЬ", article="РСВ-140807")
    index = si.build_product_index(list(Product.objects.all()))
    assert si.match_card(_card("Перфоратор Вихрь", "РСВ-140807"), "vihr", index).status == (
        "not_found"
    )
    m = si.match_card(_card("Перфоратор Вихрь П-1200К-М", "72/3/3"), "vihr", index)
    assert m.status == "matched"
    assert m.products == [p1]
    assert m.matched_by == "sku"


@pytest.mark.django_db
def test_model_fragment_with_slash_is_not_sku_key(catalog):
    """``ЭШМ-125/5Э`` — часть модели, а не артикул: ключа SKU ``125/5`` быть не должно."""
    _product(catalog, "Шлифмаш эксц РЕСАНТА ЭШМ-125/5Э", article="")
    index = si.build_product_index(list(Product.objects.all()))
    assert index.entries[0].article_keys == []
    m = si.match_card(_card("Шлифмашина Ресанта прочая", "125/5"), "resanta", index)
    assert m.status == "not_found"


@pytest.mark.django_db
def test_product_with_two_brands_indexed_under_both(catalog):
    """Имя упоминает два бренда — товар виден карточкам обоих источников."""
    p = _product(catalog, "Аккумулятор для ДА-24-2ЛК Зубр, Ресанта", article="ACC-1")
    index = si.build_product_index(list(Product.objects.all()))
    # Токены — КАНОНИЧЕСКИЕ идентичности бренда из brand_vocabulary.json, а не
    # найденные в имени подстроки: иначе потребители словаря разошлись бы по
    # нормализации. Порядок — порядок словаря, поэтому сверяем составом.
    assert set(index.entries[0].tokens) == {"ЗУБР", "РЕСАНТА"}
    assert len(index.entries[0].tokens) == 2
    for source in ("zubr", "resanta"):
        m = si.match_card(_card("Аккумулятор ДА-24-2ЛК", "ACC-1"), source, index)
        assert m.status == "matched", source
        assert m.products == [p]


@pytest.mark.django_db
def test_product_without_brand_token_stays_out_of_index(catalog):
    """Брендовый токен остаётся обязательным: он и защищает ступень SKU.

    Артикулы источников («70/6/14») сталкиваются с 1С-артикулами посторонних
    товаров, поэтому совпадение по одному лишь артикулу запрещено.
    """
    _product(catalog, "Щуп веерный 0,05-1,0 мм (20 листов)", article="70/6/14")
    index = si.build_product_index(list(Product.objects.all()))
    assert index.entries == []
    m = si.match_card(_card("Бензопила Ресанта БП-4516", "70/6/14"), "resanta", index)
    assert m.status == "not_found"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name",
    [
        "Переходник ЗУБР 3/4 на 1/2",  # дроби размеров
        "Выключатель УШМ Интерскол 125/900",  # Ø и мощность
        "Тепловентилятор ТВК-1 220-240 В, 900/1800 В Ресанта",  # два режима мощности
    ],
)
def test_two_group_numbers_in_name_are_not_sku_keys(catalog, name):
    """Двухгрупповые числа в названии — параметры, а не артикул производителя."""
    _product(catalog, name, article="")
    index = si.build_product_index(list(Product.objects.all()))
    assert index.entries[0].article_keys == []


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


# --- оси бензопил и триммеров: нормализаторы и boolean (DRF-1439) -------------


HUTER_MAP_PATH = "data/catalog_processing_rules/scraped_attr_map.benzopily-trimmery.json"


def _huter_map():
    from pathlib import Path

    return si.load_attr_map(Path(HUTER_MAP_PATH))


def _huter_extract(attributes):
    card = {
        "source_url": "https://huter.su/x/",
        "name": "Бензопила Huter BS-45",
        "brand": "Huter",
        "manufacturer_sku": "70/6/1",
        "attributes": attributes,
    }
    return si.extract_card_values(card, "huter", _huter_map())


def test_decimal_normalizer_accepts_comma():
    """Десятичная запятая источника («25,4») не уезжает в текст."""
    assert si.normalize_scalar("25,4", "decimal") == 25.4
    assert si.normalize_scalar("51,7", "decimal") == 51.7
    assert si.normalize_scalar("1,3", "decimal") == 1.3


def test_bar_length_exact_inch_snaps_to_nominal():
    """152.4 = 6.0 × 25.4 — та же 6-дюймовая шина, что источник зовёт «150/6»."""
    assert si.normalize_scalar("152.4", "bar_length_mm") == 150
    assert si.normalize_scalar("254", "bar_length_mm") == 250


@pytest.mark.parametrize("raw", ["350", "400", "450", "500", "505"])
def test_bar_length_nominal_series_untouched(raw):
    """Номиналы ряда целыми дюймами не делятся и остаются как есть."""
    assert si.normalize_scalar(raw, "bar_length_mm") == float(raw)


def test_bar_length_takes_millimetres_from_pair_field():
    """«400/16"», «150/6», «250/10”» — берётся первое число (миллиметры)."""
    assert si.normalize_scalar('400/16"', "bar_length_mm") == 400
    assert si.normalize_scalar("150/6", "bar_length_mm") == 150
    assert si.normalize_scalar("250/10”", "bar_length_mm") == 250


def test_option_key_strips_quotes_and_spaces():
    """«Easy Load», « Easy Load » и Easy Load — один ключ, а не три опции."""
    assert si.option_key("Easy Load") == "easy load"
    assert si.option_key("«Easy Load»") == "easy load"
    assert si.option_key("« Easy Load »") == "easy load"
    assert si.option_key('"Easy Load"') == "easy load"


def test_spool_type_maps_to_existing_quick_load():
    """«Тип катушки» — существующий quick_load, новая ось не заводится."""
    for raw in ("Easy Load", "«Easy Load»", "« Easy Load »"):
        values = _huter_extract({"Тип катушки": raw}).values
        assert [(v.attribute_slug, v.value) for v in values] == [("quick_load", True)]
    values = _huter_extract({"Тип катушки": "Стандартная"}).values
    assert [(v.attribute_slug, v.value) for v in values] == [("quick_load", False)]


def test_boolean_unknown_value_drops_to_report():
    res = _huter_extract({"Автоматическая смазка цепи": "Опционально"})
    assert res.values == []
    assert res.dropped and "boolean" in res.dropped[0][2]


def test_chain_pitch_broken_fraction_is_resolved_not_swallowed():
    """«1.4» — потерянная косая дроби 1/4, а не шаг 0.404 и не новая опция."""
    entry = _huter_map()["sources"]["huter"]["fields"]["Шаг цепи, дюйм"]
    assert entry["values"]["1.4"] == "pitch-1-4"
    assert entry["values"]["0.25"] == "pitch-1-4"
    assert entry["values_confidence"]["1.4"] == "low"
    values = _huter_extract({"Шаг цепи, дюйм": "1.4"}).values
    assert [(v.attribute_slug, v.value, v.confidence) for v in values] == [
        ("chain_pitch", "pitch-1-4", si.MAP_CONFIDENCE["low"])
    ]


def test_combined_field_feeds_two_axes():
    """«Толщина звена и шаг цепи, мм/дюймы» несёт две оси в одном поле."""
    got = {
        (v.attribute_slug, v.value)
        for v in _huter_extract({"Толщина звена и шаг цепи, мм/дюймы": "1,3 / 3/8"}).values
    }
    assert got == {("chain_gauge", Decimal("1.3")), ("chain_pitch", "pitch-3-8")}
    got = {
        (v.attribute_slug, v.value)
        for v in _huter_extract({"Толщина звена и шаг цепи, мм/дюймы": "1.5/0.325"}).values
    }
    assert got == {("chain_gauge", Decimal("1.5")), ("chain_pitch", "pitch-0-325")}


def test_huter_map_declares_family_scope_and_skips_foreign_tracks():
    """Карта покрывает семейство типов, не трогает tool_type, мощность и вес."""
    amap = _huter_map()
    assert amap["scope_tool_types"] == [
        "bp-benzopily",
        "bp-cepi",
        "bp-shiny",
        "bp-trimmery",
        "pily",
    ]
    managed = {
        e["attribute"]
        for _, e in si.iter_field_entries(amap["sources"]["huter"])
        if "attribute" in e
    }
    assert "tool_type" not in managed
    # мощность и вес — трек DRF-1440, карта их не мапит
    assert managed.isdisjoint({"power", "weight", "weight_kg"})


@pytest.mark.parametrize(
    "label",
    [
        "Антивибрационная система",
        "Тормоз цепи",
        "Уровень звукового давления, дБ",
        "Ширина скоса диском, мм",
        "Ширина скоса леской, мм",
    ],
)
def test_huter_map_rejects_single_valued_axes(label):
    """Оси с одним значением в замере отклонены (правило DRF-1428)."""
    entry = _huter_map()["sources"]["huter"]["fields"][label]
    assert entry["action"] == "unmapped"
    assert "DRF-1428" in entry["reason"]


# --- сквозной прогон карты benzopily-trimmery (DRF-1439) ----------------------


HUTER_ATTRS = {
    "bar_length": (AttributeType.DECIMAL, "мм"),
    "chain_pitch": (AttributeType.SELECT, ""),
    "chain_links": (AttributeType.DECIMAL, "шт."),
    "chain_gauge": (AttributeType.DECIMAL, "мм"),
    "engine_displacement": (AttributeType.DECIMAL, "см³"),
    "chain_auto_oiling": (AttributeType.BOOLEAN, ""),
    "split_shaft": (AttributeType.BOOLEAN, ""),
    "quick_load": (AttributeType.BOOLEAN, ""),
    "battery_capacity": (AttributeType.DECIMAL, "А·ч"),
    "voltage": (AttributeType.DECIMAL, "В"),
    "no_load_speed": (AttributeType.DECIMAL, "об/мин"),
    "motor_type": (AttributeType.SELECT, ""),
    "tool_type": (AttributeType.SELECT, ""),
}
HUTER_TOOL_TYPES = ["bp-benzopily", "bp-cepi", "bp-shiny", "bp-trimmery", "pily"]


@pytest.fixture
def huter_catalog(db):
    cat = Category.add_root(name="Сад", slug="sad")
    attrs = {}
    for slug, (atype, unit) in HUTER_ATTRS.items():
        attrs[slug] = Attribute.objects.create(
            slug=slug, name=slug, attribute_type=atype, unit=unit
        )
    opts = {}
    for oslug in HUTER_TOOL_TYPES:
        opts[("tool_type", oslug)] = AttributeOption.objects.create(
            attribute=attrs["tool_type"], value=oslug, slug=oslug
        )
    for oslug in ("pitch-1-4", "pitch-0-325", "pitch-3-8", "pitch-0-404"):
        opts[("chain_pitch", oslug)] = AttributeOption.objects.create(
            attribute=attrs["chain_pitch"], value=oslug, slug=oslug
        )
    for oslug in ("brushed", "brushless"):
        opts[("motor_type", oslug)] = AttributeOption.objects.create(
            attribute=attrs["motor_type"], value=oslug, slug=oslug
        )
    return {"category": cat, "attrs": attrs, "opts": opts}


def _huter_product(cat, name, article, tool_type):
    p = Product.objects.create(
        category=cat["category"],
        name=name,
        slug=f"h{Product.objects.count()}",
        article=article,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    ProductAttributeValue.objects.create(
        product=p,
        attribute=cat["attrs"]["tool_type"],
        value_option=cat["opts"][("tool_type", tool_type)],
        source=Source.RULES,
    )
    return p


def _huter_card(name, sku, attributes):
    return {
        "source_url": f"https://huter.su/{sku}/",
        "name": name,
        "brand": "Huter",
        "manufacturer_sku": sku,
        "description": None,
        "summary_raw": None,
        "attributes": attributes,
    }


def _run_huter(export_path, tmp_path, *extra):
    report_path = tmp_path / "huter_report.json"
    call_command(
        "catalog_import_scraped",
        export_path,
        "--category",
        "benzopily-trimmery",
        "--report",
        str(report_path),
        *extra,
        verbosity=0,
    )
    return json.loads(report_path.read_text(encoding="utf-8"))


@pytest.mark.django_db
def test_huter_family_scope_covers_five_tool_types(huter_catalog, tmp_path):
    """Одна карта пишет во все пять типов семейства, а не только в свой slug."""
    saw = _huter_product(huter_catalog, "Бензопила HUTER BS-45", "70/6/1", "bp-benzopily")
    chain = _huter_product(
        huter_catalog, "Цепь 36 звеньев C9 1/4 для ELS-20LI HUTER", "71/4/1", "bp-cepi"
    )
    trimmer = _huter_product(
        huter_catalog, "Триммер бензиновый Huter GGT-2500S", "70/2/13", "bp-trimmery"
    )
    export = _export(
        tmp_path,
        [
            _huter_card(
                "Бензопила Huter BS-45",
                "70/6/1",
                {
                    "Длина шины, мм/дюйм": "450/18",
                    "Толщина звена и шаг цепи, мм/дюймы": "1.5/0.325",
                    "Количество звеньев цепи, шт": "72",
                    "Объём двигателя, см³": "45",
                    "Автоматическая смазка цепи": "Есть",
                    "Антивибрационная система": "Есть",
                    "Вес, кг": "6.3 кг",
                },
            ),
            _huter_card(
                "Цепь С9 Huter для аккумуляторной пилы ELS-20Li",
                "71/4/1",
                {
                    "Длина шины, мм": "152.4",
                    "Шаг цепи, дюйм": "0.25",
                    "Количество звеньев, шт.": "36",
                },
            ),
            _huter_card(
                "Триммер бензиновый Huter GGT-2500S",
                "70/2/13",
                {
                    "Тип катушки": "«Easy Load»",
                    "Разъемная штанга": "Есть",
                    "Объём двигателя, см³": "51,7",
                    "Напряжение питающей сети, В": "220-230В, ~50 Гц",
                },
            ),
        ],
        source="huter",
    )
    report = _run_huter(export, tmp_path)
    assert report["scope_tool_types"] == HUTER_TOOL_TYPES
    assert report["stats"]["matched"] == 3

    def vals(p):
        return {
            pav.attribute.slug: (
                pav.value_option.slug
                if pav.value_option_id
                else (pav.value_boolean if pav.value_boolean is not None else pav.value_decimal)
            )
            for pav in p.attribute_values.select_related("attribute", "value_option")
            if pav.attribute.slug != "tool_type"
        }

    assert vals(saw) == {
        "bar_length": Decimal("450"),
        "chain_gauge": Decimal("1.5"),
        "chain_pitch": "pitch-0-325",
        "chain_links": Decimal("72"),
        "engine_displacement": Decimal("45"),
        "chain_auto_oiling": True,
    }
    # 152.4 = 6" ровно -> номинал 150, а не отдельное значение фасета
    assert vals(chain) == {
        "bar_length": Decimal("150"),
        "chain_pitch": "pitch-1-4",
        "chain_links": Decimal("36"),
    }
    # кавычки вокруг «Easy Load» не создали второй опции; сеть 220 В в voltage не ушла
    assert vals(trimmer) == {
        "quick_load": True,
        "split_shaft": True,
        "engine_displacement": Decimal("51.7"),
    }
    assert report["stats"]["skipped_voltage"] == 1
    # отклонённые оси остались кандидатами, а не значениями
    assert "Антивибрационная система" in report["unmapped_attributes"]
    assert "Вес, кг" in report["unmapped_attributes"]


@pytest.mark.django_db
def test_huter_boolean_second_run_is_confirm_not_conflict(huter_catalog, tmp_path):
    """Boolean-значение сравнивается как boolean: повтор — confirm, не conflict."""
    _huter_product(huter_catalog, "Бензопила HUTER BS-45", "70/6/1", "bp-benzopily")
    export = _export(
        tmp_path,
        [_huter_card("Бензопила Huter BS-45", "70/6/1", {"Автоматическая смазка цепи": "Нет"})],
        source="huter",
    )
    _run_huter(export, tmp_path)
    pav = ProductAttributeValue.objects.get(attribute__slug="chain_auto_oiling")
    assert pav.value_boolean is False
    report = _run_huter(export, tmp_path)
    assert report["stats"]["confirm"] == 1
    assert report["stats"].get("conflict", 0) == 0
