"""Тесты «вежливого» HTTP-клиента parser.client.

Сеть полностью замокана через httpx.MockTransport, time.sleep и
time.monotonic — через monkeypatch. Реальных HTTP-запросов в тестах нет.
"""

import json

import httpx
import pytest

from parser.client import AccessDeniedError, PoliteClient


class FakeClock:
    """Детерминированные time.monotonic/time.sleep для проверки троттлинга."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr("parser.client.time.sleep", fake.sleep)
    monkeypatch.setattr("parser.client.time.monotonic", fake.monotonic)
    return fake


class Recorder:
    """Хэндлер MockTransport: записывает запросы, отдаёт ответы из очереди.

    По умолчанию robots.txt отвечает 404 (ограничений нет), страницы — 200.
    """

    def __init__(self, page_responses=None, robots_body=None, robots_responses=None):
        self.requests = []
        self.page_responses = list(page_responses or [])
        self.robots_body = robots_body
        self.robots_responses = list(robots_responses or [])

    def __call__(self, request):
        self.requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            if self.robots_responses:
                status = self.robots_responses.pop(0)
                return httpx.Response(status, text=f"robots {status}")
            if self.robots_body is not None:
                return httpx.Response(200, text=self.robots_body)
            return httpx.Response(404)
        if self.page_responses:
            status = self.page_responses.pop(0)
            return httpx.Response(status, text=f"status {status}")
        return httpx.Response(200, text="page ok")

    def page_requests(self):
        return [u for u in self.requests if not u.endswith("/robots.txt")]

    def robots_requests(self):
        return [u for u in self.requests if u.endswith("/robots.txt")]


def make_client(tmp_path, handler, throttle_s=3.0):
    return PoliteClient(
        cache_dir=tmp_path / "cache",
        fetch_log_path=tmp_path / "fetch-log.jsonl",
        throttle_s=throttle_s,
        transport=httpx.MockTransport(handler),
    )


def read_log(tmp_path):
    log_path = tmp_path / "fetch-log.jsonl"
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_retry_on_500_then_success(tmp_path, clock):
    rec = Recorder(page_responses=[500, 500, 200])
    client = make_client(tmp_path, rec)
    text = client.get_text("http://example.com/catalog/drills/")
    assert text == "status 200"
    assert len(rec.page_requests()) == 3
    statuses = [e["status"] for e in read_log(tmp_path) if e["url"].endswith("/catalog/drills/")]
    assert statuses == [500, 500, 200]


def test_404_raises_without_retries(tmp_path, clock):
    rec = Recorder(page_responses=[404])
    client = make_client(tmp_path, rec)
    with pytest.raises(httpx.HTTPStatusError):
        client.get_text("http://example.com/missing")
    assert len(rec.page_requests()) == 1


def test_403_access_denied_immediately(tmp_path, clock):
    rec = Recorder(page_responses=[403])
    client = make_client(tmp_path, rec)
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/closed")
    assert len(rec.page_requests()) == 1


def test_401_access_denied_immediately(tmp_path, clock):
    rec = Recorder(page_responses=[401])
    client = make_client(tmp_path, rec)
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/closed")
    assert len(rec.page_requests()) == 1


def test_429_persistent_gives_access_denied(tmp_path, clock):
    rec = Recorder(page_responses=[429, 429, 429, 429])
    client = make_client(tmp_path, rec)
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/limited")
    # 1 попытка + 3 ретрая
    assert len(rec.page_requests()) == 4
    statuses = [e["status"] for e in read_log(tmp_path) if e["url"].endswith("/limited")]
    assert statuses == [429, 429, 429, 429]


def test_throttle_between_requests_same_host(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec, throttle_s=3.0)
    client.get_text("http://example.com/a")
    client.get_text("http://example.com/b")
    # robots идёт без сна (первый запрос на хост), страницы — с полной паузой
    assert clock.sleeps == [pytest.approx(3.0), pytest.approx(3.0)]


def test_throttle_accounts_for_elapsed(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec, throttle_s=3.0)
    client.get_text("http://example.com/a")
    clock.t += 1.0  # между запросами прошла 1 с «реального» времени
    client.get_text("http://example.com/b")
    assert clock.sleeps[-1] == pytest.approx(2.0)


def test_throttle_independent_per_host(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec)
    client.get_text("http://host-a.example/x")
    client.get_text("http://host-b.example/y")
    # у host-b свой бюджет троттлинга: robots без сна, страница — полная пауза
    assert clock.sleeps == [pytest.approx(3.0), pytest.approx(3.0)]
    clock.t += 10.0  # пауза для host-a давно выдержана
    client.get_text("http://host-a.example/z")
    assert len(clock.sleeps) == 2


def test_www_prefix_counts_as_same_host(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec)
    client.get_text("http://www.example.com/a")
    client.get_text("http://example.com/b")
    # robots закэширован на нормализованный хост — запрошен один раз
    assert len(rec.robots_requests()) == 1
    # троттлинг общий: вторая страница ждёт полную паузу после первой
    assert clock.sleeps == [pytest.approx(3.0), pytest.approx(3.0)]


def test_cache_second_fetch_hits_disk(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec)
    url = "http://example.com/card/1"
    assert client.get_text(url) == "page ok"
    assert client.get_text(url) == "page ok"
    assert len(rec.page_requests()) == 1
    entries = [e for e in read_log(tmp_path) if e["url"] == url]
    assert entries[0]["cache_hit"] is False
    assert entries[-1]["cache_hit"] is True
    assert entries[-1]["status"] == 200


def test_robots_disallow_blocks_before_request(tmp_path, clock):
    rec = Recorder(robots_body="User-agent: *\nDisallow: /private/\n")
    client = make_client(tmp_path, rec)
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/private/secret")
    assert rec.page_requests() == []  # сама страница не запрашивалась
    # разрешённый путь проходит
    assert client.get_text("http://example.com/public/ok") == "page ok"


def test_robots_fetched_once_per_host(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec)
    client.get_text("http://example.com/a")
    client.get_text("http://example.com/b")
    client.get_text("http://example.com/c")
    assert len(rec.robots_requests()) == 1


def test_robots_404_means_no_restrictions(tmp_path, clock):
    rec = Recorder(robots_responses=[404])
    client = make_client(tmp_path, rec)
    assert client.get_text("http://example.com/a") == "page ok"
    assert len(rec.robots_requests()) == 1  # без ретраев
    assert rec.page_requests() == ["http://example.com/a"]


def test_robots_5xx_then_success(tmp_path, clock):
    rec = Recorder(robots_responses=[500, 200])
    client = make_client(tmp_path, rec)
    assert client.get_text("http://example.com/a") == "page ok"
    assert len(rec.robots_requests()) == 2  # ретрай после 5xx


def test_robots_5xx_persistent_gives_access_denied(tmp_path, clock):
    rec = Recorder(robots_responses=[500, 500, 500, 500])
    client = make_client(tmp_path, rec)
    with pytest.raises(AccessDeniedError):
        client.get_text("http://example.com/catalog/drills/")
    # 1 попытка + 3 ретрая на robots; страница без robots не запрашивается
    assert len(rec.robots_requests()) == 4
    assert rec.page_requests() == []
    errors = [e.get("error") for e in read_log(tmp_path)]
    assert "robots_unavailable" in errors


def test_log_line_fields(tmp_path, clock):
    rec = Recorder()
    client = make_client(tmp_path, rec)
    client.get_text("http://example.com/a")
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
