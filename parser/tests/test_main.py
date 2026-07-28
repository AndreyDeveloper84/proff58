"""Интеграционные тесты CLI-оркестратора (parser.main) — строго без сети.

`PoliteClient` подменяется стаб-клиентом через dependency injection
(параметр `client_factory` у `main`, без monkeypatch внутренностей): стаб
отдаёт fixture-страницы по URL, фиксирует все запрошенные URL и падает
AssertionError на любом неожиданном URL — реальных HTTP-запросов нет.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parser.browser_client import BrowserRunLimitError
from parser.category import SITEMAP_URLS, collect_product_urls
from parser.client import AccessDeniedError
from parser.main import DEFAULT_CATEGORY_URLS, main
from parser.schemas import ErrorsExport, Export

FIXTURES = Path(__file__).resolve().parent / "fixtures"

ZUBR_DEFAULT_CATEGORY_URL = DEFAULT_CATEGORY_URLS["zubr"]

MINIMAL_CARD_HTML = "<html><body><h1>Перфоратор тестовый</h1></body></html>"
NO_NAME_HTML = "<html><body><p>страница не найдена</p></body></html>"


def load_fixture(domain: str, filename: str) -> str:
    return (FIXTURES / domain / filename).read_text(encoding="utf-8")


def sitemap_xml(*urls: str) -> str:
    """Минимальный sitemap с заданными <loc> в заданном порядке."""
    locs = "".join(f"<loc>{url}</loc>" for url in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset>{locs}</urlset>'


class StubClient:
    """Стаб PoliteClient: отдаёт заготовленные страницы, пишет журнал запросов."""

    def __init__(self, pages: dict[str, str], deny_urls: set[str] | None = None):
        self._pages = dict(pages)
        self._deny_urls = set(deny_urls or ())
        self.requested: list[str] = []

    def get_text(self, url: str) -> str:
        self.requested.append(url)
        if url in self._deny_urls:
            raise AccessDeniedError(f"доступ запрещён (HTTP 403), обходы не подбираем: {url}")
        if url not in self._pages:
            raise AssertionError(f"стаб-клиент: неожиданный URL {url}")
        return self._pages[url]


def run_with_stub(stub: StubClient, argv: list[str]) -> int:
    """Прогон main с подменённым клиентом (фабрика всегда отдаёт один стаб)."""
    return main(argv, client_factory=lambda **_kwargs: stub)


# --- один источник end-to-end ------------------------------------------------

RESANTA_URLS = [
    "https://resanta.ru/perforator-p-28-800k-resanta/",
    "https://resanta.ru/perforator-p-30-900k-resanta/",
    "https://resanta.ru/perforator-p-32-1000k-resanta/",
]
RESANTA_FILES = [
    "perforator-p-28-800k-resanta.html",
    "perforator-p-30-900k-resanta.html",
    "perforator-p-32-1000k-resanta.html",
]


def resanta_stub(deny_urls: set[str] | None = None) -> StubClient:
    """Стаб Ресанты: sitemap с тремя fixture-карточками перфораторов."""
    pages = {SITEMAP_URLS["resanta"]: sitemap_xml(*RESANTA_URLS)}
    for url, filename in zip(RESANTA_URLS, RESANTA_FILES, strict=True):
        pages[url] = load_fixture("resanta.ru", filename)
    return StubClient(pages, deny_urls=deny_urls)


def test_single_source_end_to_end(tmp_path):
    stub = resanta_stub()
    output = tmp_path / "products.json"
    exit_code = run_with_stub(
        stub, ["--source", "resanta", "--limit", "2", "--output", str(output)]
    )
    assert exit_code == 0
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    assert export.source == "resanta"
    assert export.schema_version == "1.0"
    assert export.category.source_url == SITEMAP_URLS["resanta"]
    assert len(export.products) == 2  # ровно лимит
    assert all(card.name for card in export.products)
    # запрошены только sitemap и две первые карточки (сработал лимит)
    assert stub.requested == [SITEMAP_URLS["resanta"], *RESANTA_URLS[:2]]
    # errors-файл по умолчанию — рядом с output, <stem>.errors.json, ошибок нет
    errors_path = tmp_path / "products.errors.json"
    errors = ErrorsExport.model_validate_json(errors_path.read_text(encoding="utf-8"))
    assert errors.source == "resanta"
    assert errors.errors == []


def test_rejected_card_goes_to_errors(tmp_path):
    good_url = RESANTA_URLS[0]
    bad_url = "https://resanta.ru/perforator-broken-card/"
    pages = {
        SITEMAP_URLS["resanta"]: sitemap_xml(good_url, bad_url),
        good_url: load_fixture("resanta.ru", RESANTA_FILES[0]),
        bad_url: NO_NAME_HTML,  # карточка без названия → ProductParseError
    }
    stub = StubClient(pages)
    output = tmp_path / "products.json"
    exit_code = run_with_stub(stub, ["--source", "resanta", "--output", str(output)])
    assert exit_code == 0  # отклонение карточки — не фатально
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    assert [card.source_url for card in export.products] == [good_url]
    errors_path = tmp_path / "products.errors.json"
    errors = ErrorsExport.model_validate_json(errors_path.read_text(encoding="utf-8"))
    assert len(errors.errors) == 1
    record = errors.errors[0]
    assert record.stage == "product"
    assert record.source_url == bad_url


# --- Интерскол: дедупликация и дефолтная маска --------------------------------

INTERSKOL_PRODUCT_URL = (
    "https://www.interskol.ru/product/perforator-sds-plus-interskol-p-24-700er-interskol"
)
INTERSKOL_DUP_URLS = [
    INTERSKOL_PRODUCT_URL,
    # та же карточка через категорийный путь
    "https://www.interskol.ru/catalog/setevoj-elektroinstrument/"
    "perforatory-sds-plus/perforator-sds-plus-interskol-p-24-700er-interskol",
    # и её «-copy»-дубль
    INTERSKOL_PRODUCT_URL + "-copy",
]


def test_interskol_dedup_single_card(tmp_path):
    card_html = load_fixture(
        "www.interskol.ru",
        "product_perforator-sds-plus-interskol-p-24-700er-interskol.html",
    )
    pages = {SITEMAP_URLS["interskol"]: sitemap_xml(*INTERSKOL_DUP_URLS)}
    pages.update({url: card_html for url in INTERSKOL_DUP_URLS})
    stub = StubClient(pages)
    output = tmp_path / "interskol.json"
    exit_code = run_with_stub(
        stub,
        ["--source", "interskol", "--category-url", "perforator", "--output", str(output)],
    )
    assert exit_code == 0
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    # три URL-дубля свелись к одной карточке
    assert len(export.products) == 1
    assert export.products[0].source_url == INTERSKOL_PRODUCT_URL
    # дубли даже не запрашивались
    assert stub.requested == [SITEMAP_URLS["interskol"], INTERSKOL_PRODUCT_URL]


def test_interskol_default_mask_skips_news_and_catalog(tmp_path):
    # широкая маска «perforator» захватила бы новость и категорию — дефолт
    # «product/perforator» отсекает всё, кроме карточек /product/…
    assert DEFAULT_CATEGORY_URLS["interskol"] == "product/perforator"
    news_url = "https://www.interskol.ru/news/perforator-novyj-2024"
    catalog_url = "https://www.interskol.ru/catalog/setevoj-elektroinstrument/perforatory"
    pages = {
        SITEMAP_URLS["interskol"]: sitemap_xml(news_url, catalog_url, INTERSKOL_PRODUCT_URL),
        INTERSKOL_PRODUCT_URL: MINIMAL_CARD_HTML,
    }
    stub = StubClient(pages)
    output = tmp_path / "out.json"
    # --category-url не передан — работает дефолт источника
    exit_code = run_with_stub(stub, ["--source", "interskol", "--output", str(output)])
    assert exit_code == 0
    assert stub.requested == [SITEMAP_URLS["interskol"], INTERSKOL_PRODUCT_URL]
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    assert [card.source_url for card in export.products] == [INTERSKOL_PRODUCT_URL]


# --- дефолтные маски resanta/vihr не захватывают категорийные URL -------------


@pytest.mark.parametrize(
    ("source", "domain"),
    [("resanta", "resanta.ru"), ("vihr", "vihr.su")],
)
def test_default_mask_excludes_category_urls(source, domain):
    # дефолтная маска — «perforator-» с дефисом: категорийные URL
    # («…/perforatory-resanta/», «…/perforatory/») под неё не попадают,
    # продуктовые («…/perforator-p-…», «…/perforator-vihr-…») — попадают
    stub = StubClient({SITEMAP_URLS[source]: load_fixture(domain, "sitemap-shop.xml")})
    urls = collect_product_urls(stub, source, DEFAULT_CATEGORY_URLS[source], limit=1000)
    assert urls, f"дефолтная маска {source} ничего не собрала из fixture-sitemap"
    assert all("perforatory" not in url for url in urls)


# --- атомарная запись ----------------------------------------------------------


def test_no_tmp_files_left_after_run(tmp_path):
    stub = resanta_stub()
    output = tmp_path / "nested" / "products.json"  # каталог создаётся на лету
    exit_code = run_with_stub(
        stub, ["--source", "resanta", "--limit", "1", "--output", str(output)]
    )
    assert exit_code == 0
    assert output.exists()
    assert (tmp_path / "nested" / "products.errors.json").exists()
    assert list(tmp_path.rglob("*.tmp")) == []


# --- --source all ---------------------------------------------------------------


def test_source_all_writes_per_source_files_and_summary(tmp_path, capsys):
    zubr_card_url = (
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/"
        "perforatory/zp-test/?ID=123"
    )
    zubr_listing = (
        '<a href="/mekhanizirovannye-instrumenty/elektroinstrumenty/'
        'perforatory/zp-test/?ID=123">card</a>'
    )
    resanta_url = "https://resanta.ru/perforator-test-resanta/"
    vihr_url = "https://vihr.su/perforator-test-vihr/"
    interskol_url = "https://www.interskol.ru/product/perforator-test-interskol"
    pages = {
        SITEMAP_URLS["resanta"]: sitemap_xml(resanta_url),
        SITEMAP_URLS["vihr"]: sitemap_xml(vihr_url),
        SITEMAP_URLS["interskol"]: sitemap_xml(interskol_url),
        ZUBR_DEFAULT_CATEGORY_URL: zubr_listing,
        resanta_url: MINIMAL_CARD_HTML,
        vihr_url: MINIMAL_CARD_HTML,
        interskol_url: MINIMAL_CARD_HTML,
        zubr_card_url: MINIMAL_CARD_HTML,
    }
    stub = StubClient(pages)
    out_dir = tmp_path / "output"
    # дефолтные --category-url всех источников (пилот «перфораторы»)
    exit_code = run_with_stub(
        stub, ["--source", "all", "--limit", "5", "--output", str(out_dir)]
    )
    assert exit_code == 0
    for source in ("resanta", "vihr", "interskol", "zubr"):
        products_path = out_dir / f"{source}.products.json"
        errors_path = out_dir / f"{source}.errors.json"
        export = Export.model_validate_json(products_path.read_text(encoding="utf-8"))
        assert export.source == source
        assert len(export.products) == 1
        errors = ErrorsExport.model_validate_json(errors_path.read_text(encoding="utf-8"))
        assert errors.errors == []
    summary = capsys.readouterr().out
    assert "ИТОГО" in summary
    assert list(out_dir.rglob("*.tmp")) == []


# --- AccessDeniedError ----------------------------------------------------------


def test_access_denied_stops_run_and_writes_partial(tmp_path, capsys):
    stub = resanta_stub(deny_urls={RESANTA_URLS[1]})
    output = tmp_path / "products.json"
    exit_code = run_with_stub(stub, ["--source", "resanta", "--output", str(output)])
    assert exit_code != 0
    # остановились на запрещённой карточке — третий URL не запрашивали
    assert stub.requested == [SITEMAP_URLS["resanta"], *RESANTA_URLS[:2]]
    # частичная выгрузка всё равно атомарно записана
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    assert [card.source_url for card in export.products] == [RESANTA_URLS[0]]
    errors_path = tmp_path / "products.errors.json"
    errors = ErrorsExport.model_validate_json(errors_path.read_text(encoding="utf-8"))
    assert len(errors.errors) == 1
    assert errors.errors[0].stage == "product"
    assert errors.errors[0].source_url == RESANTA_URLS[1]
    assert "доступ" in capsys.readouterr().err.lower()
    assert list(tmp_path.rglob("*.tmp")) == []


# --- валидация аргументов ---------------------------------------------------------


def test_throttle_below_minimum_rejected(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(
            ["--source", "resanta", "--throttle", "1.0"],
            client_factory=lambda **_kwargs: StubClient({}),
        )
    assert exc_info.value.code == 2  # ошибка argparse
    assert "троттлинг" in capsys.readouterr().err.lower()


def test_category_url_with_source_all_rejected(capsys):
    # одна маска на все 4 источника бессмысленна — отклоняем, как --errors-output
    with pytest.raises(SystemExit) as exc_info:
        main(
            ["--source", "all", "--category-url", "perforator"],
            client_factory=lambda **_kwargs: StubClient({}),
        )
    assert exc_info.value.code == 2  # ошибка argparse
    assert "--category-url" in capsys.readouterr().err


# --- режим B (браузер): флаги CLI -------------------------------------------------


def capturing_factory(stub: StubClient, captured: dict):
    """Фабрика, записывающая kwargs, с которыми main создаёт клиента."""

    def factory(**kwargs):
        captured.update(kwargs)
        return stub

    return factory


def test_default_mode_is_http(tmp_path):
    stub = resanta_stub()
    captured: dict = {}
    output = tmp_path / "products.json"
    exit_code = main(
        ["--source", "resanta", "--output", str(output)],
        client_factory=capturing_factory(stub, captured),
    )
    assert exit_code == 0
    assert captured["mode"] == "http"
    assert captured["run_limit"] == 20  # дефолтный --limit режима A не изменился


def test_mode_browser_uses_headless_factory_with_limit_100(tmp_path):
    stub = resanta_stub()
    captured: dict = {}
    output = tmp_path / "products.json"
    exit_code = main(
        ["--source", "resanta", "--mode", "browser", "--output", str(output)],
        client_factory=capturing_factory(stub, captured),
    )
    assert exit_code == 0
    assert captured["mode"] == "browser"
    assert captured["headless"] is True  # без --bootstrap — headless
    # в режиме browser дефолтный лимит — 100 (не 20)
    assert captured["run_limit"] == 100


def test_mode_browser_limit_capped_at_150(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(
            ["--source", "resanta", "--mode", "browser", "--limit", "200"],
            client_factory=lambda **_kwargs: StubClient({}),
        )
    assert exc_info.value.code == 2  # ошибка argparse
    assert "150" in capsys.readouterr().err


def test_bootstrap_without_browser_mode_rejected(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(
            ["--source", "resanta", "--bootstrap"],
            client_factory=lambda **_kwargs: StubClient({}),
        )
    assert exc_info.value.code == 2  # ошибка argparse
    assert "--bootstrap" in capsys.readouterr().err


def test_bootstrap_runs_headed_bootstrap_not_factory(tmp_path, monkeypatch):
    # --mode browser --bootstrap: headed-запуск для человека, клиент не создаётся
    calls: list[Path] = []
    monkeypatch.setattr(
        "parser.main._run_bootstrap", lambda profile_dir: calls.append(profile_dir) or 0
    )
    exit_code = main(
        ["--source", "resanta", "--mode", "browser", "--bootstrap"],
        client_factory=lambda **_kwargs: StubClient({}),
    )
    assert exit_code == 0
    assert len(calls) == 1


# --- режим B (браузер): лимит прогона считает только карточки ------------------------


class StubBrowserClient(StubClient):
    """Стаб BrowserClient: run_limit считает только запросы фазы карточек.

    Sitemap/листинг идут через тот же клиент до start_card_phase() и лимит
    не тратят (как исправленный BrowserClient). Сверх лимита в фазе карточек
    — BrowserRunLimitError.
    """

    def __init__(self, pages: dict[str, str], run_limit: int):
        super().__init__(pages)
        self._run_limit = run_limit
        self._card_phase = False
        self._fetched = 0
        self.card_phase_started = False

    def start_card_phase(self) -> None:
        self._card_phase = True
        self.card_phase_started = True

    def get_text(self, url: str) -> str:
        if self._card_phase:
            if self._fetched >= self._run_limit:
                raise BrowserRunLimitError(
                    f"исчерпан лимит {self._run_limit} карточек на прогон, "
                    f"остановка по плану: {url}"
                )
            self._fetched += 1
        return super().get_text(url)


def browser_stub(card_urls: list[str], run_limit: int) -> StubBrowserClient:
    """Стаб режима B Ресанты: sitemap + fixture-карточки, лимит на карточки."""
    pages = {SITEMAP_URLS["resanta"]: sitemap_xml(*card_urls)}
    for url, filename in zip(card_urls, RESANTA_FILES, strict=True):
        pages[url] = load_fixture("resanta.ru", filename)
    return StubBrowserClient(pages, run_limit=run_limit)


def test_browser_run_limit_counts_only_cards(tmp_path):
    # регрессия Critical 1: sitemap — cache-miss через тот же клиент, но лимит
    # не тратит: все 3 карточки при run_limit=3 получены, исключения нет
    stub = browser_stub(RESANTA_URLS, run_limit=3)
    output = tmp_path / "products.json"
    exit_code = run_with_stub(
        stub, ["--source", "resanta", "--mode", "browser", "--output", str(output)]
    )
    assert exit_code == 0
    assert stub.card_phase_started  # run_source перевёл клиент в фазу карточек
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    assert len(export.products) == 3
    assert stub.requested == [SITEMAP_URLS["resanta"], *RESANTA_URLS]


def test_browser_run_limit_is_planned_stop_exit_0(tmp_path, capsys):
    # N+1-я карточка сверх лимита — плановая остановка: exit 0, частичная
    # выгрузка записана, в stderr — про лимит, а не «доступ запрещён»
    stub = browser_stub(RESANTA_URLS, run_limit=2)
    output = tmp_path / "products.json"
    exit_code = run_with_stub(
        stub, ["--source", "resanta", "--mode", "browser", "--output", str(output)]
    )
    assert exit_code == 0
    # остановились на N+1-й карточке — её URL в браузер не уходил
    assert stub.requested == [SITEMAP_URLS["resanta"], *RESANTA_URLS[:2]]
    export = Export.model_validate_json(output.read_text(encoding="utf-8"))
    assert [card.source_url for card in export.products] == RESANTA_URLS[:2]
    errors_path = tmp_path / "products.errors.json"
    errors = ErrorsExport.model_validate_json(errors_path.read_text(encoding="utf-8"))
    assert errors.errors == []  # плановая остановка — не ошибка
    err = capsys.readouterr().err
    assert "лимит" in err and "план" in err
    assert "доступ запрещён" not in err
