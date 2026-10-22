"""Извлечение изображений из карточек и источник huter.su.

Два изменения одним треком, потому что они об одном:

1. Поле ``ProductCard.images`` завёл трек ИЗО, но **заполнения не было** —
   в ``product.py`` прямо написано «фотографии не извлекаются». Здесь оно
   появляется для Webasyst-источников из того же JSON-LD, который уже
   разбирается ради имени, бренда и sku.
2. ``huter.su`` — тот же Webasyst, что resanta и vihr, поэтому отдельного
   извлекателя не требует: только диспетчер, sitemap и список источников.

Почему huter вообще взялся: у ЗУБР/KRAFTOOL/GRINDA в ``robots.txt`` закрыт
каталог ``/upload``, где лежат картинки, а у huter.su запрета нет. Фикстура —
настоящая карточка, снятая 01.09.2026 (`benzopila-huter-bs-45`), а не
выдуманная разметка: правило проверяется на данных источника.

Отдельная ценность huter, ради которой стоит городить источник: JSON-LD отдаёт
``sku`` = **наш артикул** (``70/6/2`` у товара 1541 «Бензопила HUTER BS-45»).
Матчинг получается точным, без угадывания моделей по названию.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from parser.category import SITEMAP_URLS
from parser.product import ProductParseError, parse_product
from parser.schemas import ProductCard

FIXTURES = Path(__file__).parent / "fixtures"

HUTER_URL = "https://huter.su/benzopila-huter-bs-45/"
RESANTA_URL = "https://resanta.ru/perforator-p-30-900k-resanta/"


def load(domain: str, filename: str) -> str:
    return (FIXTURES / domain / filename).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# huter.su — источник заведён
# --------------------------------------------------------------------------- #

def test_huter_is_known_source():
    """Неизвестный источник падает с ValueError — huter падать не должен."""
    html = load("huter.su", "benzopila-huter-bs-45.html")
    card = parse_product(html, "huter", HUTER_URL)
    assert isinstance(card, ProductCard)


def test_unknown_source_still_rejected():
    """Гарантия, что диспетчер не стал принимать что попало."""
    html = load("huter.su", "benzopila-huter-bs-45.html")
    with pytest.raises(ValueError):
        parse_product(html, "no-such-source", HUTER_URL)


def test_huter_sitemap_registered():
    assert SITEMAP_URLS["huter"] == "https://huter.su/sitemap-shop.xml"


# --------------------------------------------------------------------------- #
# huter.su — разбор карточки
# --------------------------------------------------------------------------- #

def test_huter_card_fields():
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert card.name == "Бензопила Huter BS-45"
    assert card.brand == "Huter"
    assert card.description


def test_huter_sku_is_our_article():
    """Ключевое свойство источника: sku карточки совпадает с нашим артикулом.

    Товар 1541 «Бензопила HUTER BS-45» имеет article ``70/6/2``. Если источник
    перестанет отдавать sku в этом виде, матчинг придётся строить иначе — и
    узнать об этом надо тестом, а не на прогоне.
    """
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert card.manufacturer_sku == "70/6/2"


# --------------------------------------------------------------------------- #
# Изображения
# --------------------------------------------------------------------------- #

def test_huter_images_extracted():
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert card.images, "JSON-LD карточки несёт image — он обязан попасть в images"
    urls = [i.url for i in card.images]
    assert all(u.startswith("https://") for u in urls), "адреса обязаны быть абсолютными"
    assert any("wa-data" in u for u in urls)


def test_first_image_is_main():
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert card.images[0].is_main is True
    assert sum(1 for i in card.images if i.is_main) == 1


def test_resanta_images_extracted_too():
    """Правило общее для Webasyst, а не индивидуальное для huter."""
    card = parse_product(
        load("resanta.ru", "perforator-p-30-900k-resanta.html"), "resanta", RESANTA_URL
    )
    assert card.images
    assert "resanta.ru" in card.images[0].url


def test_resanta_existing_fields_unchanged():
    """Регрессия: добавление картинок не задело прежний разбор resanta."""
    card = parse_product(
        load("resanta.ru", "perforator-p-30-900k-resanta.html"), "resanta", RESANTA_URL
    )
    assert card.name == "Перфоратор Ресанта П-30-900К"
    assert card.brand == "Ресанта"
    assert card.manufacturer_sku == "75/3/2"
    assert card.attributes["Тип хвостовика"] == "SDS-PLUS"


def test_card_without_jsonld_image_has_empty_images():
    """Отсутствие image в JSON-LD — не ошибка: images просто пуст.

    Схема допускает пустой список, и карточка без фотографий обязана
    оставаться валидной (иначе донор характеристик перестанет работать там,
    где источник фото не отдаёт).
    """
    html = load("huter.su", "benzopila-huter-bs-45.html").replace('"image"', '"image_x"')
    card = parse_product(html, "huter", HUTER_URL)
    assert card.images == []
    assert card.name  # карточка по-прежнему разобралась


def test_images_deduplicated_by_url():
    """Один и тот же адрес в галерее и превью не должен дать два ImageRef."""
    from bs4 import BeautifulSoup

    from parser.product import _jsonld_images

    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"X",
     "image":["https://huter.su/a.png","https://huter.su/a.png","https://huter.su/b.png"]}
    </script></head><body></body></html>
    """
    refs = _jsonld_images(BeautifulSoup(html, "lxml"))
    card = ProductCard(source_url=HUTER_URL, name="X", images=refs)
    assert [i.url for i in card.images] == ["https://huter.su/a.png", "https://huter.su/b.png"]


def test_jsonld_image_as_single_string():
    """image может быть строкой, а не списком — у huter именно так."""
    from bs4 import BeautifulSoup

    from parser.product import _jsonld_images

    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"X",
     "image":"https://huter.su/one.png"}
    </script></head><body></body></html>
    """
    refs = _jsonld_images(BeautifulSoup(html, "lxml"))
    assert [r.url for r in refs] == ["https://huter.su/one.png"]


def test_relative_image_url_rejected_not_crashed():
    """Относительный адрес схема не примет — извлекатель обязан его отбросить.

    Ронять всю карточку из-за одной кривой ссылки нельзя: характеристики с неё
    всё равно нужны.
    """
    from bs4 import BeautifulSoup

    from parser.product import _jsonld_images

    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"X",
     "image":["/relative/a.png","https://huter.su/good.png"]}
    </script></head><body></body></html>
    """
    refs = _jsonld_images(BeautifulSoup(html, "lxml"))
    assert [r.url for r in refs] == ["https://huter.su/good.png"]


# --------------------------------------------------------------------------- #
# Сбор URL: у huter карточки плоские, категории — под /category/
# --------------------------------------------------------------------------- #

class _StubClient:
    """Отдаёт заранее заданный sitemap. Сети нет."""

    def __init__(self, xml: str) -> None:
        self._xml = xml
        self.requested: list[str] = []

    def get_text(self, url: str) -> str:
        self.requested.append(url)
        return self._xml


_HUTER_SITEMAP = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://huter.su/category/elektrogeneratory-huter/</loc></url>
  <url><loc>https://huter.su/category/sadovaya-i-benzotekhnika-huter/</loc></url>
  <url><loc>https://huter.su/benzopila-huter-bs-45/</loc></url>
  <url><loc>https://huter.su/motobur-huter-ggd-52/</loc></url>
  <url><loc>https://huter.su/motopompa-huter-mpd-80/</loc></url>
</urlset>
"""


def test_huter_category_urls_are_not_taken_for_cards():
    """Категории huter содержат ту же подстроку, что карточки, и маской не режутся.

    Без явного исключения `/category/` сборщик потащил бы категорийные страницы
    как товары: они не разберутся и засорят errors.json, а лимит карточек будет
    съеден впустую.
    """
    from parser.category import collect_product_urls

    client = _StubClient(_HUTER_SITEMAP)
    urls = collect_product_urls(client, "huter", "huter.su/", limit=10)

    assert urls == [
        "https://huter.su/benzopila-huter-bs-45/",
        "https://huter.su/motobur-huter-ggd-52/",
        "https://huter.su/motopompa-huter-mpd-80/",
    ]


def test_huter_limit_respected():
    from parser.category import collect_product_urls

    client = _StubClient(_HUTER_SITEMAP)
    assert len(collect_product_urls(client, "huter", "huter.su/", limit=2)) == 2


# --------------------------------------------------------------------------- #
# Статические страницы huter не должны попадать в товары
# --------------------------------------------------------------------------- #

def test_huter_static_page_rejected():
    """Оферта, «Компания», «Политика» лежат в том же sitemap, что карточки.

    Боевой прогон 02.09.2026 показал дефект: из пяти первых URL четыре были
    статическими страницами, и все четыре прошли как «товары» — с пустыми
    sku, брендом, характеристиками и картинками. Причина: извлекатель Webasyst
    при отсутствии JSON-LD берёт имя из первого <h1>, а <h1> есть и у оферты.

    Различитель чистый: у статической страницы huter **нет ни одного блока
    JSON-LD** (проверено на настоящей странице), у карточки есть
    ``@type=Product``. Фикстура — урезанная настоящая страница: полная весит
    295 КБ, оставлены title, блоки JSON-LD (их ноль) и <h1>.
    """
    html = load("huter.su", "public-oferta-trimmed.html")
    with pytest.raises(ProductParseError):
        parse_product(html, "huter", "https://huter.su/public-oferta/")


def test_huter_real_card_still_accepted():
    """Регрессия к предыдущему: правило не должно отсекать настоящую карточку."""
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert card.manufacturer_sku == "70/6/2"
    assert card.images


def test_resanta_h1_fallback_preserved():
    """У resanta fallback на <h1> остаётся: правило заведено только для huter.

    Ужесточать resanta нельзя — его sitemap фильтруется маской категории и
    статические страницы туда не попадают, а fallback заведён под карточки,
    где JSON-LD неполон.
    """
    html = """
    <html><head><title>Перфоратор</title></head>
    <body><h1>Перфоратор Ресанта П-30-900К</h1></body></html>
    """
    card = parse_product(html, "resanta", RESANTA_URL)
    assert card.name == "Перфоратор Ресанта П-30-900К"
    assert card.images == []


# --------------------------------------------------------------------------- #
# Характеристики huter: своя разметка, не resanta-шная
# --------------------------------------------------------------------------- #

def test_huter_attributes_extracted():
    """huter кладёт характеристики в `.product__features--item`, не в таблицу.

    Боевой прогон 02.09.2026 дал шесть принятых карточек и у всех `хар. 0`:
    селекторы resanta (`div.product-features table`) на huter не находят ничего.
    Разметка ближе к vihr — пары «title / value» в блоках.

    Значения сырые, как на сайте, — нормализация единиц не здесь.
    """
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert card.attributes, "17 характеристик на карточке обязаны попасть в выгрузку"
    assert card.attributes["Объём двигателя, см³"] == "45"
    assert card.attributes["Длина шины, мм/дюйм"] == "450/18"
    assert card.attributes["Тормоз цепи"] == "Есть"


def test_huter_price_labels_not_in_attributes():
    """Общий отсев цен продолжает действовать и для huter."""
    card = parse_product(load("huter.su", "benzopila-huter-bs-45.html"), "huter", HUTER_URL)
    assert not any("цена" in k.lower() for k in card.attributes)
