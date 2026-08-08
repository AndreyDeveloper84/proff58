"""Разделяемая механика добычи страниц для режимов A (HTTP) и B (браузер).

Общее для `PoliteClient` и `BrowserClient`: нормализация хоста, раскладка
дискового кэша (`<хост>/<sha256>.html` + `.json`-мета), журнал доступа JSONL
и robots.txt (свой matcher по RFC 9309 с кэшем на хост). Политики
(троттлинг/темп, ретраи/стоп) у режимов разные и в клиентах остаются.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit


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


# Символы, которые НЕ перекодируем при нормализации пути. `%` — чтобы уже
# закодированное не кодировалось повторно; `*` и `$` — метасимволы шаблона.
_ROBOTS_SAFE = "/*$?&=:@%+,;~-._!()'"


def _normalize_robots_path(path: str) -> str:
    """Одна нормализация для обеих сторон сравнения (правило и URL).

    Иначе кириллица в robots («/каталог/») никогда не совпадёт с `%D0%BA…` в
    URL: сравнивать надо приведённое к одному виду (RFC 9309 §2.2.2).
    """
    return quote(path, safe=_ROBOTS_SAFE)


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Шаблон robots → regex.

    `*` — любая последовательность символов; `$` **в самом конце** — конец
    строки (в середине это обычный символ). Всё остальное экранируется.
    """
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    expr = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile("^" + expr + ("$" if anchored else ""))


@dataclass(frozen=True)
class _RobotsRule:
    """Строка Allow/Disallow: шаблон, его длина (специфичность) и regex."""

    allow: bool
    pattern: str
    regex: re.Pattern[str]

    @property
    def length(self) -> int:
        return len(self.pattern)


class _RobotsGroup:
    """Группа `User-agent: …` и её правила."""

    def __init__(self) -> None:
        self.agents: list[str] = []
        self.rules: list[_RobotsRule] = []


class RobotsRules:
    """Разобранный robots.txt с сопоставлением путей по RFC 9309.

    Отличия от `urllib.robotparser`, ради которых он и заменён (ИЗО-05):

    - `*` внутри правила — любая последовательность, а не литерал (медиа-запреты
      resanta.ru и vihr.su записаны именно так);
    - `$` в конце правила — якорь конца строки;
    - выигрывает **самое длинное** совпавшее правило, а не первое по порядку;
      при равной длине выигрывает `Allow`.
    """

    def __init__(self, groups: list[_RobotsGroup]):
        self._groups = groups

    def _rules_for(self, user_agent: str) -> list[_RobotsRule]:
        """Группа для нашего UA: именованная точнее `*` (как и в robotparser)."""
        token = user_agent.split("/")[0].strip().lower()
        wildcard: list[_RobotsRule] | None = None
        for group in self._groups:
            for agent in group.agents:
                if agent == "*":
                    if wildcard is None:
                        wildcard = group.rules
                elif agent and agent in token:
                    return group.rules
        return wildcard if wildcard is not None else []

    def can_fetch(self, user_agent: str, url: str) -> bool:
        rules = self._rules_for(user_agent)
        if not rules:
            return True
        target = _request_path(url)
        best: _RobotsRule | None = None
        for rule in rules:
            if not rule.regex.match(target):
                continue
            if (
                best is None
                or rule.length > best.length
                or (rule.length == best.length and rule.allow)
            ):
                best = rule
        return True if best is None else best.allow


def _request_path(url: str) -> str:
    """Путь запроса для сверки с robots: path + query, без схемы и хоста."""
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return _normalize_robots_path(path)


def parse_robots(text: str) -> RobotsRules:
    """Разбор robots.txt в группы.

    Пустое значение `Disallow:`/`Allow:` — не правило (первое по RFC значит
    «ограничений нет», второе не определено); строки без `:` и комментарии
    после `#` отбрасываются. Правила до первого `User-agent` игнорируются.
    """
    groups: list[_RobotsGroup] = []
    current: _RobotsGroup | None = None
    start_new_group = True

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field in ("user-agent", "useragent"):
            if start_new_group or current is None:
                current = _RobotsGroup()
                groups.append(current)
                start_new_group = False
            current.agents.append(value.lower())
        elif field in ("allow", "disallow"):
            # следующая строка User-agent начнёт новую группу
            start_new_group = True
            if current is None or not value:
                continue
            pattern = _normalize_robots_path(value)
            current.rules.append(
                _RobotsRule(
                    allow=(field == "allow"),
                    pattern=pattern,
                    regex=_pattern_to_regex(pattern),
                )
            )
    return RobotsRules(groups)


class RobotsGate:
    """Кэш разобранного robots по хосту; текст robots отдаёт фетчер клиента.

    Контракт фетчера: `fetcher(robots_url) -> str | None` — текст robots;
    пустая строка — «ограничений нет» (4xx); None — robots недоступен
    (после всех ретраев режима A или одной попытки режима B).
    """

    def __init__(self, *, user_agent: str, fetcher: Callable[[str], str | None]):
        self._user_agent = user_agent
        self._fetcher = fetcher
        self._rules: dict[str, RobotsRules] = {}

    def can_fetch(self, url: str) -> bool:
        """True — путь разрешён; RobotsUnavailableError — robots недоступен."""
        host = normalize_host(url)
        rules = self._rules.get(host)
        if rules is None:
            robots_url = robots_url_for(url)
            text = self._fetcher(robots_url)
            if text is None:
                raise RobotsUnavailableError(robots_url)
            rules = parse_robots(text)
            self._rules[host] = rules
        return rules.can_fetch(self._user_agent, url)
