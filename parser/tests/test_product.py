"""Тесты извлечения карточек товаров (parser.product) — строго без сети.

Все карточки парсятся из сохранённого HTML в fixtures/. Ожидаемые значения
сверены с документом docs/parser-mvp/source-structure.md и сами fixtures.
"""

from pathlib import Path

import pytest

from parser.product import _PRICE_KEY_RE, ProductParseError, parse_product
from parser.schemas import ProductCard

FIXTURES = Path(__file__).resolve().parent / "fixtures"

RESANTA_URL = "https://resanta.ru/perforator-p-30-900k-resanta/"
VIHR_URL = "https://vihr.su/perforator-vihr-p-650k/"
INTERSKOL_URL = (
    "https://www.interskol.ru/product/perforator-sds-plus-interskol-p-24-700er-interskol"
)
ZUBR_URL = (
    "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/"
    "perforatory/perforator-sds-plus-s-metallicheskim-reduktorom-zp-28-800-k-2akr/?ID=909013"
)


def load_fixture(domain: str, filename: str) -> str:
    return (FIXTURES / domain / filename).read_text(encoding="utf-8")


def assert_no_price_keys(card: ProductCard) -> None:
    # паттерн — из parser.product (_PRICE_KEY_RE), не копия: иначе дрейф
    # копии ослабит гарантию «цены не попадают в attributes»
    for key in card.attributes:
        assert not _PRICE_KEY_RE.search(key), f"в attributes попал ключ цены/наличия: {key!r}"


# --- resanta.ru ------------------------------------------------------------


def test_resanta_card_full():
    html = load_fixture("resanta.ru", "perforator-p-30-900k-resanta.html")
    card = parse_product(html, "resanta", RESANTA_URL)
    assert isinstance(card, ProductCard)
    # SEO-хвост « в Москве» отрезан
    assert card.name == "Перфоратор Ресанта П-30-900К"
    assert card.brand == "Ресанта"
    assert card.manufacturer_sku == "75/3/2"
    assert card.description  # JSON-LD description непустой
    # сырые значения как есть: диапазон оборотов — строка
    assert card.attributes["Частота вращения, об/мин"] == "0-1100"
    assert card.attributes["Напряжение питающей сети, В"] == "220-230В, ~50 Гц"
    assert card.attributes["Тип хвостовика"] == "SDS-PLUS"
    assert card.attributes["Энергия удара, Дж"] == "4.3"
    # короткая таблица (4 строки) + полная (15 строк) с дедупликацией
    assert len(card.attributes) == 16
    # краткая сводка — единственный носитель мощности у Ресанты
    assert card.summary_raw is not None
    assert "Вт" in card.summary_raw
    assert "900 Вт" in card.summary_raw
    assert_no_price_keys(card)


@pytest.mark.parametrize(
    "filename,sku,name",
    [
        ("perforator-p-28-800k-resanta.html", "75/3/1", "Перфоратор Ресанта П-28-800К"),
        ("perforator-p-32-1000k-resanta.html", "75/3/3", "Перфоратор Ресанта П-32-1000К"),
    ],
)
def test_resanta_other_cards(filename, sku, name):
    html = load_fixture("resanta.ru", filename)
    card = parse_product(html, "resanta", RESANTA_URL)
    assert card.name == name
    assert card.manufacturer_sku == sku
    assert card.attributes["Тип хвостовика"] == "SDS-PLUS"
    assert card.summary_raw and "Вт" in card.summary_raw
    assert_no_price_keys(card)


# --- vihr.su ---------------------------------------------------------------


def test_vihr_card_full():
    html = load_fixture("vihr.su", "perforator-vihr-p-650k.html")
    card = parse_product(html, "vihr", VIHR_URL)
    assert isinstance(card, ProductCard)
    assert card.name == "Перфоратор Вихрь П-650К"
    assert card.brand == "Вихрь"
    assert card.manufacturer_sku == "72/3/5"
    # у ВИХРЯ мощность есть в таблице (в отличие от Ресанты)
    assert card.attributes["Мощность, Вт"] == "650"
    assert card.attributes["Частота вращения, об/мин"] == "0-1000"
    assert card.attributes["Тип хвостовика"] == "SDS-PLUS"
    assert len(card.attributes) == 15
    assert card.summary_raw is not None
    assert "650 Вт" in card.summary_raw
    assert_no_price_keys(card)


@pytest.mark.parametrize(
    "filename,sku,power",
    [
        ("perforator-vihr-p-800k.html", "72/3/6", "800"),
        ("perforator-vihr-p-900k.html", "72/3/2", "900"),
    ],
)
def test_vihr_other_cards(filename, sku, power):
    html = load_fixture("vihr.su", filename)
    card = parse_product(html, "vihr", VIHR_URL)
    assert card.manufacturer_sku == sku
    assert card.attributes["Мощность, Вт"] == power
    assert card.summary_raw and "Вт" in card.summary_raw
    assert_no_price_keys(card)


# --- interskol.ru ----------------------------------------------------------


def test_interskol_card_full():
    html = load_fixture(
        "www.interskol.ru", "product_perforator-sds-plus-interskol-p-24-700er-interskol.html"
    )
    card = parse_product(html, "interskol", INTERSKOL_URL)
    assert isinstance(card, ProductCard)
    # h1 содержит только модель — это нормально, name непустое
    assert card.name == "П-24/700ЭР"
    assert card.manufacturer_sku == "160.1.0.00"
    # свойства из RSC-payload, сырые значения (slug'и не сохраняем)
    assert card.attributes["Тип хвостовика"] == "sds-plus"
    assert card.attributes["Мощность, Вт."] == "720"
    assert card.attributes["Тип двигателя"] == "щеточный"
    # мусор в данных не чистим: «Реверс: щеточный» — как есть
    assert card.attributes["Реверс"] == "щеточный"
    assert card.attributes["Вес, кг"] == "3.3"
    assert len(card.attributes) == 26
    assert_no_price_keys(card)


# --- zubr.ru ---------------------------------------------------------------


def test_zubr_card_full():
    html = load_fixture(
        "zubr.ru",
        "mekhanizirovannye-instrumenty_elektroinstrumenty_perforatory_perforato_c3ec0c3a.html",
    )
    card = parse_product(html, "zubr", ZUBR_URL)
    assert isinstance(card, ProductCard)
    # h1 (с моделью после <br>) предпочтительнее title (там только серия)
    assert card.name == "Перфоратор SDS-plus с металлическим редуктором ЗП-28-800 К"
    assert card.manufacturer_sku == "ЗП-28-800 К"
    assert card.attributes["Напряжение питания, В/Гц"] == "230/50"
    assert card.attributes["Мощность, Вт"] == "800"
    assert card.attributes["Частота вращения шпинделя, об/мин"] == "0-1200"
    assert card.attributes["Патрон"] == "SDS Plus"
    # мобильный блок не задвоил строки: вариантов подписей с пробелом
    # перед запятой («Мощность , Вт») быть не должно
    for key in card.attributes:
        assert " ," not in key, f"дубль из мобильного блока: {key!r}"
    # «Кейс» — первое вхождение (спецификация), не комплектационное «1»
    assert card.attributes["Кейс"] == "есть"
    assert_no_price_keys(card)


# --- ошибки ----------------------------------------------------------------


@pytest.mark.parametrize("source", ["resanta", "vihr", "interskol", "zubr"])
def test_html_without_name_raises(source):
    with pytest.raises(ProductParseError):
        parse_product("<html><head></head><body></body></html>", source, RESANTA_URL)


def test_unknown_source_raises():
    with pytest.raises(ValueError, match="неизвестный источник"):
        parse_product("<html></html>", "makita", RESANTA_URL)
