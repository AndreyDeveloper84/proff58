"""Извлечение карточек товаров из HTML четырёх источников (Phase 2).

`parse_product(html, source, url)` превращает сохранённую страницу карточки
в `ProductCard`. Структура источников зафиксирована в
`docs/parser-mvp/source-structure.md` (разведка Phase 1):

- resanta.ru  — JSON-LD `Product` + HTML-таблицы характеристик (Webasyst);
- vihr.su     — JSON-LD `Product` + блоки `dl--product__features--item`;
- interskol.ru — RSC-payload Next.js (`self.__next_f.push`), отдельный разбор;
- zubr.ru     — HTML-таблицы «параметр — значение» (Bitrix), мобильные дубли.

Цены и фотографии не извлекаются. Значения атрибутов — сырые, как на сайте
(нормализация единиц — Phase 3); ключ — исходная подпись поля.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup
from pydantic import ValidationError

from parser.schemas import ProductCard

# Подписи цены/наличия в attributes недопустимы (цены не извлекаем — ТЗ).
# Паттерн узкий, по словам: «Наличие режима долбления» (фича Интерскола)
# относится к характеристикам и НЕ должно отсекаться.
_PRICE_KEY_RE = re.compile(
    r"\b(цена|цены|стоимость|price|availability)\b|^в\s+наличии$|^наличие$",
    re.IGNORECASE,
)

# Мягкий перенос (U+00AD, HTML `&shy;`) — типографский артефакт вёрстки
# (у ЗУБРа «ще&shy;точ&shy;ный»), к данным отношения не имеет — выкидываем.
_SOFT_HYPHEN = "\u00ad"

# SEO-хвосты названий Webasyst (Ресанта/Вихрь): «… купить …», «… в интернет-
# магазине …», «… в Москве». Правило: режем всё от первого маркера до конца.
_SEO_TAIL_RE = re.compile(
    r"\s+(?:купить\s.*|в\s+интернет-магазине\s.*|в\s+москве\s*)$", re.IGNORECASE
)

# RSC-payload Интерскола: свойства вида
# {"property": {"name": …, "slug": …}, "value": {"value": …, "slug": …}}
_INTERSKOL_PAIR_RE = re.compile(
    r'"property":\{[^{}]*"name":"(.*?)","slug":"(.*?)"\},'
    r'"value":\{[^{}]*"value":"(.*?)","slug":"(.*?)"\}'
)
_INTERSKOL_CODE_RE = re.compile(r'"code":"([^"]+)"')
_INTERSKOL_ARTICLE_HTML_RE = re.compile(r"Артикул:\s*(?:<!--\s*-->)?([^<]{1,30})")

# У старых/сетевых моделей Интерскола (например, Д-10/300ЭР) характеристики не
# inlined в RSC payload, а опубликованы в rich-text описании в формате
# "Параметр: значение". Отсекаем типовые единицы измерения при нормализации ключа.
_INTERSKOL_DESC_UNIT_RE = re.compile(
    r"\s*,\s*(?:об/мин|мин|Вт|мм|дюйм|А|В/Гц|кг|л(?:ет)?)\s*$",
    re.IGNORECASE,
)


class ProductParseError(Exception):
    """Карточка не извлеклась (нет имени, битый HTML и т.п.) — товар отклоняется."""


def parse_product(html: str, source: str, url: str) -> ProductCard:
    """HTML карточки → ProductCard; диспетчер по источнику."""
    extractors = {
        "resanta": _parse_resanta,
        "vihr": _parse_vihr,
        "interskol": _parse_interskol,
        "zubr": _parse_zubr,
    }
    extractor = extractors.get(source)
    if extractor is None:
        raise ValueError(
            f"неизвестный источник: {source!r} (ожидаются: {', '.join(sorted(extractors))})"
        )
    fields = extractor(html)
    name = _clean(fields.get("name") or "")
    if not name:
        raise ProductParseError(f"карточка без названия отклоняется: {url}")
    fields["name"] = name
    try:
        return ProductCard(source_url=url, **fields)
    except ValidationError as exc:
        raise ProductParseError(f"карточка не прошла валидацию схемы: {url}: {exc}") from exc


# --- общие помощники --------------------------------------------------------


def _clean(text: str) -> str:
    """Убрать мягкие переносы и схлопнуть пробелы (дублирует очистку схемы)."""
    return re.sub(r"\s+", " ", text.replace(_SOFT_HYPHEN, "")).strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _add_pair(attributes: dict[str, str], label: str, value: str) -> None:
    """Пара «подпись — значение»: очистка, отсев цен, дедупликация по подписи."""
    label = _clean(label)
    value = _clean(value)
    if not label or not value:
        return
    if _PRICE_KEY_RE.search(label):
        return
    # дедупликация по подписи: первое вхождение побеждает; ключ сравнения
    # без пробелов перед знаками препинания (мобильный дубль ЗУБРа «Мощность , Вт»)
    dedup_key = re.sub(r"\s+([,;:!?])", r"\1", label)
    for existing in attributes:
        if re.sub(r"\s+([,;:!?])", r"\1", existing) == dedup_key:
            return
    attributes[label] = value


def _jsonld_product(soup: BeautifulSoup) -> dict | None:
    """Первый блок JSON-LD с @type=Product (dict), иначе None."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def _strip_seo_tail(name: str) -> str:
    """Отрезать SEO-хвост названия Webasyst (см. _SEO_TAIL_RE)."""
    return _SEO_TAIL_RE.sub("", name).strip()


def _first_h1(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    return h1.get_text(separator=" ") if h1 else ""


def _title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    return tag.get_text() if tag else ""


def _table_pairs(table, attributes: dict[str, str]) -> None:
    """Строки таблицы с 2+ ячейками → пары (первая ячейка — подпись)."""
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) >= 2:
            _add_pair(attributes, cells[0].get_text(), cells[1].get_text())


# --- resanta.ru / vihr.su (Webasyst, JSON-LD) -------------------------------


def _webasyst_fields(soup: BeautifulSoup) -> dict:
    """Общая часть Webasyst-карточек: JSON-LD Product → name/brand/sku/description."""
    product = _jsonld_product(soup) or {}
    brand = product.get("brand")
    brand_name = brand.get("name") if isinstance(brand, dict) else None
    name = _strip_seo_tail(product.get("name") or "") or _first_h1(soup)
    return {
        "name": name,
        "brand": brand_name,
        "manufacturer_sku": product.get("sku"),
        "description": product.get("description"),
    }


def _parse_resanta(html: str) -> dict:
    soup = _soup(html)
    fields = _webasyst_fields(soup)
    attributes: dict[str, str] = {}
    # короткая таблица над вкладками (div.product-features, 4 строки) и полная
    # во вкладке (div#product-features, 15 строк); дедупликация по подписи
    for table in soup.select("div.product-features table, div#product-features table"):
        _table_pairs(table, attributes)
    # краткая сводка («SDS-Plus, 900 Вт, …») — единственный носитель мощности
    summary = soup.select_one("div.product-page meta[itemprop='description']")
    fields["attributes"] = attributes
    fields["summary_raw"] = summary.get("content") if summary else None
    return fields


def _parse_vihr(html: str) -> dict:
    soup = _soup(html)
    fields = _webasyst_fields(soup)
    attributes: dict[str, str] = {}
    for item in soup.select("div.dl--product__features--item"):
        name_tag = item.select_one(".dl--product__features--item__name")
        value_tag = item.select_one(".dl--product__features--item__value")
        if name_tag and value_tag:
            _add_pair(attributes, name_tag.get_text(), value_tag.get_text())
    summary = soup.select_one("div.dl--product__cart--summary")
    fields["attributes"] = attributes
    fields["summary_raw"] = summary.get_text() if summary else None
    return fields


# --- interskol.ru (Next.js, RSC-payload) -------------------------------------


def _unescape_rsc(html: str) -> str:
    """Распаковка экранированного JSON из self.__next_f.push (логика dig_interskol)."""
    return html.replace('\\\\"', '"').replace('\\"', '"')


def _parse_interskol_description_specs(soup, attributes: dict[str, str]) -> None:
    """Fallback: у ряда страниц Интерскола характеристики живут только
    в rich-text блоке ``unfolding-list-right`` в виде ``Параметр: значение``.
    """
    for container in soup.find_all("div", class_=lambda c: c and "unfolding-list-right" in c):
        for line in container.get_text("\n", strip=True).splitlines():
            if ":" not in line:
                continue
            label, _, value = line.partition(":")
            label = _INTERSKOL_DESC_UNIT_RE.sub("", label).strip()
            value = value.strip()
            if label and value:
                _add_pair(attributes, label, value)


def _parse_interskol(html: str) -> dict:
    soup = _soup(html)
    unescaped = _unescape_rsc(html)
    attributes: dict[str, str] = {}
    # slug'и свойств не сохраняем (схема — подписи), но они стабильны
    # и доступны в payload при надобности (tiphvostovika, moschnostvt, …)
    for prop_name, _prop_slug, value, _value_slug in _INTERSKOL_PAIR_RE.findall(unescaped):
        _add_pair(attributes, prop_name, value)
    code = _INTERSKOL_CODE_RE.search(unescaped)
    if code:
        sku = code.group(1)
    else:
        article = _INTERSKOL_ARTICLE_HTML_RE.search(html)
        sku = article.group(1) if article else None
    # У старых/сетевых моделей (Д-10/300ЭР и др.) RSC-свойства отсутствуют,
    # но спецификация есть в HTML-описании.
    if not attributes:
        _parse_interskol_description_specs(soup, attributes)
    # h1 содержит только модель («П-24/700ЭР») — это нормально
    return {
        "name": _first_h1(soup) or _title(soup),
        "manufacturer_sku": sku,
        "attributes": attributes,
    }


# --- zubr.ru (Bitrix, HTML-таблицы) ------------------------------------------


def _parse_zubr(html: str) -> dict:
    soup = _soup(html)
    attributes: dict[str, str] = {}
    # Спецификация — table.articles-table; те же строки дублируются в мобильных
    # таблицах (с пробелом перед запятой в подписях) — дедупликация в _add_pair.
    # Строки комплектации («Перфоратор: 1») тоже идут в attributes как есть.
    for table in soup.find_all("table"):
        _table_pairs(table, attributes)
    # h1 содержит серию и модель через <br>; title — только серию, поэтому h1 лучше
    return {
        "name": _first_h1(soup) or _title(soup),
        "manufacturer_sku": attributes.get("Артикул"),
        "attributes": attributes,
    }
