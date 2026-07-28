"""Тесты браузерного клиента режима B (parser.browser_client) — без сети.

Playwright подменяется фейковым context/page (через `launcher`), robots —
фейковым фетчером (через `robots_fetcher`), паузы — monkeypatch
time.sleep/random.uniform. Реального браузера и сети в тестах нет,
кроме smoke-теста на about:blank (без внешней сети).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from parser.browser_client import (
    BrowserChallengeError,
    BrowserClient,
    BrowserRunLimitError,
)
from parser.client import AccessDeniedError

PAGE_HTML = "<html><body><h1>Карточка товара</h1></body></html>"
CHALLENGE_HTML = "<html><body>Подтвердите, что вы не робот</body></html>"


class FakeRoute:
    """Фейк playwright Route: фиксирует abort/continue_."""

    def __init__(self, resource_type: str):
        self.request = SimpleNamespace(resource_type=resource_type)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class FakeResponse:
    def __init__(self, status: int):
        self.status = status


class FakePage:
    """Фейк playwright Page: goto отдаёт очередной результат контекста."""

    def __init__(self, context: FakeContext):
        self._context = context
        self.goto_calls: list[str] = []
        self.url = "about:blank"
        self.closed = False

    def goto(self, url: str, wait_until: str | None = None):
        self.goto_calls.append(url)
        self.url = url
        status, html = self._context.results.pop(0)
        self._context.last_html = html
        return FakeResponse(status)

    def content(self) -> str:
        return self._context.last_html

    def close(self):
        self.closed = True


class FakeContext:
    """Фейк playwright BrowserContext: страницы, route, storage_state."""

    def __init__(self, results: list[tuple[int, str]] | None = None):
        # очередь (status, html) — по одному результату на page.goto
        self.results = list(results or [])
        self.last_html = ""
        self.routes: list[tuple[str, object]] = []
        self.pages: list[FakePage] = []
        self.cookies: list[dict] = []
        self.storage_state_paths: list[str] = []
        self.closed = False

    def route(self, pattern: str, handler):
        self.routes.append((pattern, handler))

    def new_page(self) -> FakePage:
        page = FakePage(self)
        self.pages.append(page)
        return page

    def add_cookies(self, cookies: list[dict]):
        self.cookies.extend(cookies)

    def storage_state(self, path: str):
        self.storage_state_paths.append(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"cookies": self.cookies}), encoding="utf-8")

    def close(self):
        self.closed = True

    # тестовый хелпер: сколько раз реально уходили в браузер
    def goto_count(self) -> int:
        return sum(len(page.goto_calls) for page in self.pages)


def make_client(
    tmp_path,
    context: FakeContext | None = None,
    *,
    pace_s=(5.0, 10.0),
    run_limit=100,
    robots_text="",
) -> tuple[BrowserClient, FakeContext]:
    """Клиент с фейковым браузером; robots_fetcher отдаёт robots_text."""
    context = context or FakeContext(results=[(200, PAGE_HTML)])
    client = BrowserClient(
        cache_dir=tmp_path / "cache",
        fetch_log_path=tmp_path / "fetch-log.jsonl",
        profile_dir=tmp_path / "profile",
        pace_s=pace_s,
        run_limit=run_limit,
        launcher=lambda: context,
        robots_fetcher=lambda _robots_url: robots_text,
    )
    return client, context


def read_log(tmp_path):
    log_path = tmp_path / "fetch-log.jsonl"
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def queue_page(context: FakeContext, status: int = 200, html: str = PAGE_HTML):
    context.results.append((status, html))


# --- темп (5–10 с между карточками) -------------------------------------------


def test_pace_between_two_fetches(tmp_path, monkeypatch):
    context = FakeContext(results=[(200, PAGE_HTML), (200, PAGE_HTML)])
    client, _ = make_client(tmp_path, context)
    sleeps: list[float] = []
    monkeypatch.setattr("parser.browser_client.time.sleep", sleeps.append)
    client.start_card_phase()
    client.get_text("http://example.com/card/1")
    client.get_text("http://example.com/card/2")
    # перед первой карточкой паузы нет, перед второй — в диапазоне [5, 10]
    assert len(sleeps) == 1
    assert 5.0 <= sleeps[0] <= 10.0


def test_pace_uses_configured_range(tmp_path, monkeypatch):
    context = FakeContext(results=[(200, PAGE_HTML), (200, PAGE_HTML)])
    client, _ = make_client(tmp_path, context, pace_s=(6.0, 8.0))
    uniforms: list[tuple[float, float]] = []
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "parser.browser_client.random.uniform",
        lambda a, b: uniforms.append((a, b)) or 7.0,
    )
    client.start_card_phase()
    client.get_text("http://example.com/card/1")
    client.get_text("http://example.com/card/2")
    assert uniforms == [(6.0, 8.0)]


# --- челлендж: стоп без ретраев -------------------------------------------------


def test_challenge_marker_in_html_raises_and_no_retry(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, CHALLENGE_HTML)])
    client, _ = make_client(tmp_path, context)
    with pytest.raises(BrowserChallengeError):
        client.get_text("http://example.com/card/1")
    assert context.goto_count() == 1  # ни одного повторного захода


def test_403_raises_challenge_error_and_no_retry(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(403, PAGE_HTML)])
    client, _ = make_client(tmp_path, context)
    with pytest.raises(BrowserChallengeError):
        client.get_text("http://example.com/card/1")
    assert context.goto_count() == 1


def test_429_raises_challenge_error(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(429, PAGE_HTML)])
    client, _ = make_client(tmp_path, context)
    with pytest.raises(BrowserChallengeError):
        client.get_text("http://example.com/card/1")


def test_challenge_error_is_access_denied(tmp_path, monkeypatch):
    # run_source ловит AccessDeniedError — челлендж должен останавливать прогон
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(403, PAGE_HTML)])
    client, _ = make_client(tmp_path, context)
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/card/1")


def test_challenge_reported_to_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, CHALLENGE_HTML)])
    client, _ = make_client(tmp_path, context)
    with pytest.raises(BrowserChallengeError):
        client.get_text("http://example.com/card/1")
    assert "СТОП" in capsys.readouterr().err


# --- кэш ------------------------------------------------------------------------


def test_second_fetch_same_url_served_from_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML)])
    client, _ = make_client(tmp_path, context)
    url = "http://example.com/card/1"
    assert client.get_text(url) == PAGE_HTML
    assert client.get_text(url) == PAGE_HTML
    assert context.goto_count() == 1  # page.goto второй раз не вызывался
    entries = [e for e in read_log(tmp_path) if e["url"] == url]
    assert entries[0]["cache_hit"] is False
    assert entries[-1]["cache_hit"] is True
    assert entries[-1]["status"] == 200


def test_cache_layout_matches_http_mode(tmp_path, monkeypatch):
    # тот же формат каталога, что у режима A: <хост>/<sha256>.html + .json
    import hashlib

    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    client, _ = make_client(tmp_path)
    url = "http://www.example.com/card/1"
    client.get_text(url)
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    # хост нормализуется без www, как в PoliteClient
    assert (tmp_path / "cache" / "example.com" / f"{key}.html").exists()
    meta = json.loads(
        (tmp_path / "cache" / "example.com" / f"{key}.json").read_text(encoding="utf-8")
    )
    assert meta["url"] == url
    assert meta["status"] == 200


# --- журнал ----------------------------------------------------------------------


def test_log_line_fields_with_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    client, _ = make_client(tmp_path)
    client.get_text("http://example.com/card/1")
    entries = read_log(tmp_path)
    assert entries, "журнал доступа пуст"
    required = {
        "ts",
        "url",
        "final_url",
        "status",
        "bytes",
        "elapsed_s",
        "throttle_wait_s",
        "cache_hit",
    }
    for entry in entries:
        assert required <= set(entry), f"в строке журнала нет полей: {entry}"
        assert entry["mode"] == "browser"


# --- route abort: фото/медиа/шрифты не грузим -------------------------------------


def test_route_abort_handler_registered_and_cuts_heavy(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    client, context = make_client(tmp_path)
    client.get_text("http://example.com/card/1")
    assert context.routes, "route-обработчик не зарегистрирован"
    pattern, handler = context.routes[0]
    assert pattern == "**/*"
    for heavy in ("image", "media", "font"):
        route = FakeRoute(heavy)
        handler(route, route.request)
        assert route.aborted, f"{heavy} должен резаться"
        assert not route.continued
    route = FakeRoute("document")
    handler(route, route.request)
    assert route.continued
    assert not route.aborted


# --- run_limit --------------------------------------------------------------------


def test_run_limit_stops_run(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML)])
    client, _ = make_client(tmp_path, context, run_limit=1)
    client.start_card_phase()
    assert client.get_text("http://example.com/card/1") == PAGE_HTML
    with pytest.raises(BrowserRunLimitError, match="лимит"):
        client.get_text("http://example.com/card/2")
    assert context.goto_count() == 1  # N+1-я карточка в браузер не уходила


def test_collect_phase_requests_do_not_eat_card_limit(tmp_path, monkeypatch):
    # регрессия Critical 1: sitemap/листинг идут через тот же клиент,
    # но лимит карточек не тратят — все N карточек при run_limit=N получены
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML)] * 4)
    client, _ = make_client(tmp_path, context, run_limit=2)
    # фаза сбора: запросы в браузер ходят, лимит не расходуется
    assert client.get_text("http://example.com/sitemap.xml") == PAGE_HTML
    assert client.get_text("http://example.com/listing/1") == PAGE_HTML
    client.start_card_phase()
    assert client.get_text("http://example.com/card/1") == PAGE_HTML
    assert client.get_text("http://example.com/card/2") == PAGE_HTML
    with pytest.raises(BrowserRunLimitError):
        client.get_text("http://example.com/card/3")
    assert context.goto_count() == 4


def test_run_limit_error_is_not_access_denied(tmp_path, monkeypatch):
    # плановая остановка — не AccessDeniedError: run_source не должен
    # докладывать «доступ запрещён» на штатном полном прогоне
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    assert not issubclass(BrowserRunLimitError, AccessDeniedError)
    context = FakeContext(results=[(200, PAGE_HTML)])
    client, _ = make_client(tmp_path, context, run_limit=1)
    client.start_card_phase()
    client.get_text("http://example.com/card/1")
    with pytest.raises(BrowserRunLimitError):
        client.get_text("http://example.com/card/2")


@pytest.mark.parametrize("status", [404, 500])
def test_error_status_not_cached(tmp_path, monkeypatch, status):
    # Important 2: ошибочные статусы в кэш не пишем (как режим A — только 200),
    # повторный get_text снова идёт в page.goto
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(status, PAGE_HTML), (status, PAGE_HTML)])
    client, _ = make_client(tmp_path, context)
    url = "http://example.com/card/1"
    assert client.get_text(url) == PAGE_HTML
    assert client.get_text(url) == PAGE_HTML
    assert context.goto_count() == 2


def test_robots_not_fetched_after_limit_exhausted(tmp_path, monkeypatch):
    # Important 3: проверка лимита раньше robots — после исчерпания лимита
    # лишний запрос за robots.txt не уходит
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML)])
    robots_calls: list[str] = []
    client = BrowserClient(
        cache_dir=tmp_path / "cache",
        fetch_log_path=tmp_path / "fetch-log.jsonl",
        profile_dir=tmp_path / "profile",
        run_limit=1,
        launcher=lambda: context,
        robots_fetcher=lambda url: robots_calls.append(url) or "",
    )
    client.start_card_phase()
    client.get_text("http://example.com/card/1")
    with pytest.raises(BrowserRunLimitError):
        client.get_text("http://example.com/card/2")
    assert robots_calls == ["http://example.com/robots.txt"]


# --- robots ------------------------------------------------------------------------


def test_robots_disallow_blocks_before_goto(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML)])
    client, _ = make_client(tmp_path, context, robots_text="User-agent: *\nDisallow: /private/\n")
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/private/secret")
    assert context.goto_count() == 0  # до goto дело не дошло
    # разрешённый путь проходит
    assert client.get_text("http://example.com/public/ok") == PAGE_HTML


def test_robots_unavailable_gives_access_denied(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML)])
    client = BrowserClient(
        cache_dir=tmp_path / "cache",
        fetch_log_path=tmp_path / "fetch-log.jsonl",
        profile_dir=tmp_path / "profile",
        launcher=lambda: context,
        robots_fetcher=lambda _robots_url: None,  # robots недоступен
    )
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/card/1")
    assert context.goto_count() == 0  # обход без robots запрещён


def test_robots_fetched_once_per_host(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    context = FakeContext(results=[(200, PAGE_HTML), (200, PAGE_HTML)])
    robots_calls: list[str] = []
    client = BrowserClient(
        cache_dir=tmp_path / "cache",
        fetch_log_path=tmp_path / "fetch-log.jsonl",
        profile_dir=tmp_path / "profile",
        launcher=lambda: context,
        robots_fetcher=lambda url: robots_calls.append(url) or "",
    )
    client.get_text("http://example.com/card/1")
    client.get_text("http://example.com/card/2")
    assert robots_calls == ["http://example.com/robots.txt"]


# --- close: сессия сохраняется -------------------------------------------------------


def test_close_saves_storage_state_next_to_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    client, context = make_client(tmp_path)
    client.get_text("http://example.com/card/1")
    client.close()
    assert context.closed
    assert context.storage_state_paths, "storage_state не сохранён"
    saved = Path(context.storage_state_paths[0])
    assert saved.exists()
    # рядом с каталогом профиля
    assert saved.parent == tmp_path


def test_storage_state_cookies_loaded_on_start(tmp_path, monkeypatch):
    monkeypatch.setattr("parser.browser_client.time.sleep", lambda _s: None)
    state_path = tmp_path / "profile.storage-state.json"
    cookie = {"name": "sid", "value": "x", "domain": "example.com", "path": "/"}
    state_path.write_text(json.dumps({"cookies": [cookie]}), encoding="utf-8")
    client, context = make_client(tmp_path)
    client.get_text("http://example.com/card/1")
    assert context.cookies == [cookie]
    client.close()


# --- bootstrap: страница закрывается ---------------------------------------------


def test_bootstrap_closes_page(tmp_path, monkeypatch):
    # Minor 4: bootstrap не должен оставлять открытую page (как get_text)
    monkeypatch.setattr("builtins.input", lambda _prompt="": None)
    client, context = make_client(tmp_path)
    client.bootstrap()
    assert context.pages, "bootstrap не открыл страницу"
    assert all(page.closed for page in context.pages)


# --- smoke: реальный headless chromium, без внешней сети -------------------------------


@pytest.mark.smoke
def test_playwright_headless_about_blank_smoke(tmp_path):
    """Headless chromium открывает about:blank — Playwright рабочий.

    Внешней сети нет: только about:blank. Доказывает, что установленный
    playwright + chromium способен поднять persistent context.
    """
    client = BrowserClient(
        cache_dir=tmp_path / "cache",
        profile_dir=tmp_path / "profile",
    )
    try:
        context = client._ensure_context()
        page = context.new_page()
        page.goto("about:blank")
        assert page.content() is not None
        page.close()
    finally:
        client.close()
