"""Разделяемая механика добычи страниц для режимов A (HTTP) и B (браузер).

Общее для `PoliteClient` и `BrowserClient`: нормализация хоста, раскладка
дискового кэша (`<хост>/<sha256>.html` + `.json`-мета), журнал доступа JSONL
и robots.txt (robotparser с кэшем на хост). Политики (троттлинг/темп,
ретраи/стоп) у режимов разные и в клиентах остаются.
"""

from __future__ import annotations

import hashlib
import json
import urllib.robotparser
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


def normalize_host(url: str) -> str:
    """Хост для троттлинга/кэша/robots: нижний регистр, без префикса www."""
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[len("www.") :]
    return host


# --- дисковый кэш страниц -------------------------------------------------------


def cache_paths(cache_dir: Path, url: str) -> tuple[Path, Path]:
    """Пути `<хост>/<sha256(url)>.html` и `.json`-меты в кэше."""
    host = normalize_host(url) or "_unknown"
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return (
        cache_dir / host / f"{key}.html",
        cache_dir / host / f"{key}.json",
    )


def read_cache(cache_dir: Path, url: str) -> tuple[str, dict] | None:
    """(текст, мета) из кэша; None — страницы в кэше нет."""
    html_path, meta_path = cache_paths(cache_dir, url)
    if not html_path.exists():
        return None
    text = html_path.read_text(encoding="utf-8")
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    return text, meta


def write_cache(
    cache_dir: Path, url: str, *, text: str, final_url: str, status: int | None
) -> None:
    """Запись страницы и меты (url, final_url, status) в кэш."""
    html_path, meta_path = cache_paths(cache_dir, url)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(text, encoding="utf-8")
    meta = {"url": url, "final_url": final_url, "status": status}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


# --- журнал доступа JSONL ---------------------------------------------------------


def append_fetch_log(
    fetch_log_path: Path,
    *,
    url: str,
    final_url: str | None,
    status: int | None,
    byte_count: int,
    elapsed_s: float,
    throttle_wait_s: float,
    cache_hit: bool,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """Строка журнала доступа JSONL — артефакт приёмки троттлинга/темпа.

    `extra` — дополнительные поля режима (например, {"mode": "browser"}).
    """
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "url": url,
        "final_url": final_url,
        "status": status,
        "bytes": byte_count,
        "elapsed_s": elapsed_s,
        "throttle_wait_s": throttle_wait_s,
        "cache_hit": cache_hit,
    }
    if error:
        record["error"] = error
    if extra:
        record.update(extra)
    fetch_log_path.parent.mkdir(parents=True, exist_ok=True)
    with fetch_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- robots.txt ---------------------------------------------------------------------


def robots_url_for(page_url: str) -> str:
    """URL robots.txt для страницы (схема и netloc как у страницы)."""
    parts = urlsplit(page_url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


class RobotsUnavailableError(Exception):
    """robots.txt не получен: обход хоста без robots запрещён (RFC 9309)."""


class RobotsGate:
    """Кэш robotparser по хосту; текст robots отдаёт фетчер клиента.

    Контракт фетчера: `fetcher(robots_url) -> str | None` — текст robots;
    пустая строка — «ограничений нет» (4xx); None — robots недоступен
    (после всех ретраев режима A или одной попытки режима B).
    """

    def __init__(self, *, user_agent: str, fetcher: Callable[[str], str | None]):
        self._user_agent = user_agent
        self._fetcher = fetcher
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        """True — путь разрешён; RobotsUnavailableError — robots недоступен."""
        host = normalize_host(url)
        parser = self._parsers.get(host)
        if parser is None:
            robots_url = robots_url_for(url)
            text = self._fetcher(robots_url)
            if text is None:
                raise RobotsUnavailableError(robots_url)
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(text.splitlines())
            self._parsers[host] = parser
        return parser.can_fetch(self._user_agent, url)
