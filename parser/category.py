"""Сбор URL карточек товаров по источнику (Phase 2).

`collect_product_urls(client, source, category_url, limit)` возвращает
дедуплицированный список URL карточек в порядке источника. Структура
источников — по разведке Phase 1 (`docs/parser-mvp/source-structure.md`):

- resanta.ru, vihr.su, interskol.ru — из sitemap (URL — константы модуля);
  `category_url` здесь — маска-подстрока для фильтрации `<loc>` sitemap
  (дефолты пилота перфораторов — в `parser.main`; маска должна быть
  достаточно узкой: у Интерскола под `perforator` попадают и новости, и
  разделы, у resanta/vihr — категорийные `perforatory`; отбор карточек
  для парсинга делает CLI по контракту задачи);
- zubr.ru — sitemap сломан (ведёт на тестовый домен), обход через страницу
  категории: `category_url` — URL листинга, карточки извлекаются по паттерну
  `…/?ID=<число>`, пагинация — по ссылке «Показать еще товар»
  (`div.js-add-product[data-page]`), с потолком `ZUBR_MAX_PAGES`.

У Интерскола один товар живёт под несколькими URL (`/product/<slug>`,
`/catalog/…/<slug>`, `…-copy`) — дедупликация по нормализованному
product-slug (`interskol_url_key`), остаётся первый URL в порядке sitemap.

Чистые помощники (`parse_sitemap`, `interskol_url_key`, `parse_zubr_listing`)
offline и тестируются без клиента; весь HTTP — только через `PoliteClient`.
"""

from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urljoin, urlsplit

from parser.client import PoliteClient

# URL sitemap — константы источников (Phase 1, зафиксировано в ТЗ Phase 2).
SITEMAP_URLS = {
    "resanta": "https://resanta.ru/sitemap-shop.xml",
    "vihr": "https://vihr.su/sitemap-shop.xml",
    # huter.su — та же платформа Webasyst, тот же путь карты товаров.
    # robots.txt разрешает карточки (закрыты корзина, фильтры, /search).
    "huter": "https://huter.su/sitemap-shop.xml",
    "interskol": "https://www.interskol.ru/sitemap.xml",
}

SUPPORTED_SOURCES = frozenset(SITEMAP_URLS) | {"zubr"}

# Потолок страниц пагинации ЗУБРа — страховка от зацикленной пагинации.
ZUBR_MAX_PAGES = 10

_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")

# Карточка ЗУБРа: ссылка, оканчивающаяся на «/?ID=<число>» (Bitrix).
_ZUBR_CARD_RE = re.compile(r'href="([^"]+/\?ID=\d+)"')

# «Показать еще товар»: ссылка на следующую страницу в data-page.
_ZUBR_NEXT_RE = re.compile(r'data-page="([^"]*PAGEN_1=\d+[^"]*)"')


def parse_sitemap(xml_text: str, mask: str) -> list[str]:
    """`<loc>` sitemap, содержащие подстроку `mask`, в порядке документа."""
    return [loc for loc in _LOC_RE.findall(xml_text) if mask in loc]


def interskol_url_key(url: str) -> str:
    """Ключ дедупликации Интерскола: последний сегмент пути, без «-copy».

    Один и тот же товар встречается в sitemap как `/product/<slug>`,
    `/catalog/…/<slug>` (в т.ч. с мусорно продублированными сегментами пути)
    и с хвостом `-copy` — всё это один ключ.
    """
    path = urlsplit(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1].lower()
    if slug.endswith("-copy"):
        slug = slug[: -len("-copy")]
    return slug


def parse_zubr_listing(html: str, page_url: str) -> tuple[list[str], str | None]:
    """URL карточек (абсолютные, без дублей) и URL следующей страницы.

    Следующая страница — из `data-page` блока «Показать еще товар»
    (AJAX-endpoint Bitrix, отдаёт HTML-фрагмент листинга); None, если
    блока нет (последняя страница).
    """
    urls: list[str] = []
    seen: set[str] = set()
    for href in _ZUBR_CARD_RE.findall(html):
        absolute = urljoin(page_url, html_lib.unescape(href))
        if absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)
    next_url: str | None = None
    match = _ZUBR_NEXT_RE.search(html)
    if match:
        next_url = urljoin(page_url, html_lib.unescape(match.group(1)))
    return urls, next_url


def collect_product_urls(
    client: PoliteClient, source: str, category_url: str, limit: int
) -> list[str]:
    """URL карточек источника: дедуп, порядок источника, не более `limit`.

    Семантика `category_url` по источникам — см. docstring модуля:
    для sitemap-источников это маска-подстрока, для zubr — URL листинга.
    """
    if source not in SUPPORTED_SOURCES:
        raise ValueError(
            f"неизвестный source: {source!r} (ожидается один из {sorted(SUPPORTED_SOURCES)})"
        )
    if limit <= 0:
        return []
    if source == "zubr":
        return _collect_zubr(client, category_url, limit)
    return _collect_sitemap(client, source, category_url, limit)


# --- внутреннее ------------------------------------------------------------


def _collect_sitemap(client: PoliteClient, source: str, mask: str, limit: int) -> list[str]:
    """URL из sitemap источника; у Интерскола — дедуп по product-slug."""
    xml_text = client.get_text(SITEMAP_URLS[source])
    urls = parse_sitemap(xml_text, mask)
    if source == "huter":
        # У huter карточки лежат плоско (`/benzopila-huter-bs-45/`), а разделы —
        # под `/category/`. Обе группы содержат одну и ту же подстроку (домен),
        # поэтому маской они не разделяются. Без явного исключения сборщик
        # потащил бы категорийные страницы как товары: они не разберутся,
        # засорят errors.json и съедят лимит карточек впустую.
        urls = [u for u in urls if "/category/" not in u]
    if source == "interskol":
        urls = _dedup_by_key(urls, interskol_url_key)
    else:
        urls = _dedup_by_key(urls, key=str)
    return urls[:limit]


def _collect_zubr(client: PoliteClient, category_url: str, limit: int) -> list[str]:
    """Обход листинга ЗУБРа с пагинацией и потолком страниц."""
    urls: list[str] = []
    seen: set[str] = set()
    visited_pages: set[str] = set()
    page_url: str | None = category_url
    pages = 0
    while page_url is not None and len(urls) < limit and pages < ZUBR_MAX_PAGES:
        if page_url in visited_pages:
            break  # зацикленная пагинация — выходим даже до потолка
        visited_pages.add(page_url)
        html = client.get_text(page_url)
        pages += 1
        page_urls, page_url = parse_zubr_listing(html, page_url)
        for url in page_urls:
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls[:limit]


def _dedup_by_key(urls: list[str], key) -> list[str]:
    """Дедуп с сохранением порядка: остаётся первый URL каждого ключа."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        k = key(url)
        if k not in seen:
            seen.add(k)
            result.append(url)
    return result
