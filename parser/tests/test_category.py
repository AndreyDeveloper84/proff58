"""Тесты сбора URL карточек (parser.category) — строго без сети.

Sitemap-XML и листинг ЗУБРа берутся из fixtures/ (копии разведки Phase 1,
`scratchpad/parser-mvp/fixtures/`). Сетевая функция `collect_product_urls`
гоняется на стаб-клиенте с тем же интерфейсом, что у `PoliteClient`
(`get_text(url) -> str`), — реальных HTTP-запросов в тестах нет.
"""

import re
from pathlib import Path

import pytest

from parser.category import (
    SITEMAP_URLS,
    ZUBR_MAX_PAGES,
    collect_product_urls,
    interskol_url_key,
    parse_sitemap,
    parse_zubr_listing,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

ZUBR_CATEGORY_URL = (
    "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/perforatory/"
)
# из fixture-листинга ЗУБРа (div.js-add-product, «Показать еще товар»)
ZUBR_PAGE2_URL = (
    "https://zubr.ru/ajax/classifier_filter.php"
    "?SECTION=all&PARENT_SECTION=12177&PAGEN_1=2&AJAX_PAGE=Y&LAST_SECTION_ID=12179"
)


def load_fixture(domain: str, filename: str) -> str:
    return (FIXTURES / domain / filename).read_text(encoding="utf-8")


class StubClient:
    """Стаб PoliteClient: отдаёт заготовленные страницы, пишет журнал запросов."""

    def __init__(self, pages: dict[str, str] | None = None):
        self._pages = dict(pages or {})
        self.requested: list[str] = []

    def get_text(self, url: str) -> str:
        self.requested.append(url)
        if url not in self._pages:
            raise AssertionError(f"стаб-клиент: неожиданный URL {url}")
        return self._pages[url]


# --- parse_sitemap -----------------------------------------------------------


def sitemap_locs(xml_text: str, mask: str) -> list[str]:
    """Независимая выборка <loc> по маске — эталон для проверки порядка."""
    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml_text)
    return [loc for loc in locs if mask in loc]


@pytest.mark.parametrize(
    ("domain", "filename"),
    [
        ("resanta.ru", "sitemap-shop.xml"),
        ("vihr.su", "sitemap-shop.xml"),
        ("www.interskol.ru", "sitemap.xml"),
    ],
)
def test_parse_sitemap_perforator_nonempty_and_ordered(domain, filename):
    xml_text = load_fixture(domain, filename)
    urls = parse_sitemap(xml_text, "perforator")
    assert urls, f"маска perforator ничего не нашла в {domain}/{filename}"
    assert all("perforator" in url for url in urls)
    # порядок результата = порядок <loc> в XML
    assert urls == sitemap_locs(xml_text, "perforator")


def test_parse_sitemap_mask_without_matches():
    xml_text = load_fixture("resanta.ru", "sitemap-shop.xml")
    assert parse_sitemap(xml_text, "takoj-maski-net-nigde") == []


# --- interskol_url_key -------------------------------------------------------


def test_interskol_url_key_product_path():
    assert interskol_url_key(
        "https://www.interskol.ru/product/perforator-sds-plus-interskol-p-24-700er-interskol"
    ) == "perforator-sds-plus-interskol-p-24-700er-interskol"


def test_interskol_url_key_catalog_path_same_product():
    product = "https://www.interskol.ru/product/trehrezhimnyy-perforator-interskol-p-25-750er"
    catalog = (
        "https://www.interskol.ru/catalog/setevoj-elektroinstrument/"
        "perforatory-sds-plus/trehrezhimnyy-perforator-interskol-p-25-750er"
    )
    assert interskol_url_key(product) == interskol_url_key(catalog)


def test_interskol_url_key_strips_copy_suffix():
    original = (
        "https://www.interskol.ru/product/perforator-sds-plus-interskol-p-26-800err-interskol"
    )
    copy_url = original + "-copy"
    catalog_copy = (
        "https://www.interskol.ru/catalog/setevoj-elektroinstrument/"
        "perforatory-sds-plus/perforator-sds-plus-interskol-p-26-800err-interskol-copy"
    )
    assert interskol_url_key(copy_url) == interskol_url_key(original)
    assert interskol_url_key(catalog_copy) == interskol_url_key(original)


def test_interskol_url_key_nested_catalog_path():
    # мусорный дублированный путь из реального sitemap Интерскола
    nested = (
        "https://www.interskol.ru/catalog/setevoj-elektroinstrument/perforatory-sds-plus/"
        "setevoj-elektroinstrument/perforatory-sds-plus/"
        "perforator-sds-plus-interskol-p-32-1100avs-interskol"
    )
    flat = "https://www.interskol.ru/product/perforator-sds-plus-interskol-p-32-1100avs-interskol"
    assert interskol_url_key(nested) == interskol_url_key(flat)


def test_interskol_url_key_ignores_query_and_case():
    url = "https://www.interskol.ru/product/Perforator-P-25-750ER/?from=catalog#specs"
    assert interskol_url_key(url) == "perforator-p-25-750er"


# --- parse_zubr_listing ------------------------------------------------------


def test_zubr_listing_extracts_card_urls():
    html = load_fixture(
        "zubr.ru", "mekhanizirovannye-instrumenty_elektroinstrumenty_perforatory.html"
    )
    urls, _next = parse_zubr_listing(html, ZUBR_CATEGORY_URL)
    # fixture-страница: 20 уникальных карточек (SDS-plus сетевые ЗУБР/Патриот)
    assert len(urls) == 20
    assert all(url.startswith("https://zubr.ru/") for url in urls)
    assert len(set(urls)) == len(urls), "дубли в URL карточек"
    assert (
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/perforatory/"
        "perforator-sds-plus-s-metallicheskim-reduktorom/zp-28-800-k-2akr/?ID=909013"
    ) in urls


def test_zubr_listing_next_page_url():
    html = load_fixture(
        "zubr.ru", "mekhanizirovannye-instrumenty_elektroinstrumenty_perforatory.html"
    )
    _urls, next_url = parse_zubr_listing(html, ZUBR_CATEGORY_URL)
    assert next_url == ZUBR_PAGE2_URL


def test_zubr_listing_without_next_page():
    html = (
        '<a href="/mekhanizirovannye-instrumenty/elektroinstrumenty/perforatory/'
        'perforatory-sds-plus/zp-18-470-2akn/?ID=515623">card</a>'
    )
    urls, next_url = parse_zubr_listing(html, ZUBR_CATEGORY_URL)
    assert urls == [
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/"
        "perforatory/perforatory-sds-plus/zp-18-470-2akn/?ID=515623"
    ]
    assert next_url is None


# --- collect_product_urls: sitemap-источники ---------------------------------


@pytest.mark.parametrize(
    ("source", "domain", "filename"),
    [
        ("resanta", "resanta.ru", "sitemap-shop.xml"),
        ("vihr", "vihr.su", "sitemap-shop.xml"),
        ("interskol", "www.interskol.ru", "sitemap.xml"),
    ],
)
def test_collect_sitemap_sources_single_request(source, domain, filename):
    xml_text = load_fixture(domain, filename)
    client = StubClient({SITEMAP_URLS[source]: xml_text})
    urls = collect_product_urls(client, source, "perforator", limit=1000)
    # HTTP уходит только на sitemap источника
    assert client.requested == [SITEMAP_URLS[source]]
    expected = sitemap_locs(xml_text, "perforator")
    if source == "interskol":
        assert len(urls) <= len(expected)  # дедуп по product-slug
    else:
        assert urls == expected


@pytest.mark.parametrize("source", ["resanta", "vihr", "interskol"])
def test_collect_sitemap_limit_trims(source):
    domain = {"resanta": "resanta.ru", "vihr": "vihr.su",
              "interskol": "www.interskol.ru"}[source]
    filename = "sitemap.xml" if source == "interskol" else "sitemap-shop.xml"
    xml_text = load_fixture(domain, filename)
    client = StubClient({SITEMAP_URLS[source]: xml_text})
    urls = collect_product_urls(client, source, "perforator", limit=3)
    assert len(urls) == 3


def test_collect_interskol_dedup_end_to_end():
    xml_text = load_fixture("www.interskol.ru", "sitemap.xml")
    client = StubClient({SITEMAP_URLS["interskol"]: xml_text})
    urls = collect_product_urls(client, "interskol", "perforator", limit=10000)
    keys = [interskol_url_key(url) for url in urls]
    assert len(keys) == len(set(keys)), "после дедупа остались повторы product-slug"
    # П-26/800ЭРР есть в sitemap и как /product/…, и как /catalog/…-copy —
    # остаётся один URL, первый по порядку sitemap
    key = "perforator-sds-plus-interskol-p-26-800err-interskol"
    survivors = [url for url, k in zip(urls, keys, strict=False) if k == key]
    assert survivors == [
        "https://www.interskol.ru/product/perforator-sds-plus-interskol-p-26-800err-interskol"
    ]


# --- collect_product_urls: zubr ----------------------------------------------


def test_collect_zubr_single_page():
    html = load_fixture(
        "zubr.ru", "mekhanizirovannye-instrumenty_elektroinstrumenty_perforatory.html"
    )
    # урезанный листинг без «Показать еще товар» — следующей страницы нет
    html = re.sub(r'<div class="add-product js-add-product".*?</div>', "", html)
    client = StubClient({ZUBR_CATEGORY_URL: html})
    urls = collect_product_urls(client, "zubr", ZUBR_CATEGORY_URL, limit=100)
    assert client.requested == [ZUBR_CATEGORY_URL]
    assert len(urls) == 20
    assert len(set(urls)) == 20


def test_collect_zubr_pagination():
    listing = load_fixture(
        "zubr.ru", "mekhanizirovannye-instrumenty_elektroinstrumenty_perforatory.html"
    )
    page2_html = (
        '<a href="/mekhanizirovannye-instrumenty/elektroinstrumenty/perforatory/'
        'perforatory-sds-plus/zp-999-test/?ID=999999">p2-card-1</a>'
        # повтор карточки со страницы 1 — дедуп обязан её отбросить
        '<a href="/mekhanizirovannye-instrumenty/elektroinstrumenty/perforatory/'
        'perforator-sds-plus-s-metallicheskim-reduktorom/zp-28-800-k-2akr/?ID=909013">'
        "p2-dup</a>"
    )
    client = StubClient({ZUBR_CATEGORY_URL: listing, ZUBR_PAGE2_URL: page2_html})
    urls = collect_product_urls(client, "zubr", ZUBR_CATEGORY_URL, limit=100)
    assert client.requested == [ZUBR_CATEGORY_URL, ZUBR_PAGE2_URL]
    assert len(urls) == 21  # 20 со стр. 1 + 1 новая со стр. 2 (дубль отброшен)
    assert urls[-1].endswith("/zp-999-test/?ID=999999")


def test_collect_zubr_limit_stops_without_next_page():
    listing = load_fixture(
        "zubr.ru", "mekhanizirovannye-instrumenty_elektroinstrumenty_perforatory.html"
    )
    client = StubClient({ZUBR_CATEGORY_URL: listing})
    urls = collect_product_urls(client, "zubr", ZUBR_CATEGORY_URL, limit=5)
    assert len(urls) == 5
    # лимит набран на первой странице — вторая не запрашивается
    assert client.requested == [ZUBR_CATEGORY_URL]


def test_collect_zubr_pagination_ceiling():
    """«Следующая страница» зациклена с ростом номера — обрыв по потолку."""

    class EndlessClient(StubClient):
        def get_text(self, url: str) -> str:
            self.requested.append(url)
            page_no = len(self.requested)
            return (
                f'<a href="/catalog/perforatory/zp-{page_no}/?ID={page_no}">c</a>'
                f'<div class="add-product js-add-product" '
                f'data-page="/ajax/classifier_filter.php?PAGEN_1={page_no + 1}" '
                f'data-count="">Показать еще товар</div>'
            )

    client = EndlessClient()
    urls = collect_product_urls(client, "zubr", ZUBR_CATEGORY_URL, limit=1000)
    assert len(client.requested) == ZUBR_MAX_PAGES
    assert len(urls) == ZUBR_MAX_PAGES  # по одной новой карточке на страницу


def test_collect_unknown_source():
    client = StubClient()
    with pytest.raises(ValueError, match="source"):
        collect_product_urls(client, "unknown", "perforator", limit=10)
    assert client.requested == []


@pytest.mark.parametrize("limit", [0, -5])
def test_collect_nonpositive_limit_returns_empty_without_requests(limit):
    client = StubClient()
    assert collect_product_urls(client, "resanta", "perforator", limit=limit) == []
    assert client.requested == []  # до сети не дошло
