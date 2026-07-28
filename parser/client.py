"""«Вежливый» HTTP-клиент для парсера сайтов производителей.

Ограничения (Phase 2): последовательные запросы без параллелизма, троттлинг
по хосту (по умолчанию 3 с), ретраи только на 429/5xx, немедленная остановка
на 401/403, соблюдение robots.txt, кэш страниц на диске, журнал доступа JSONL.
Скачивается только текст страниц: фотографии не скачиваются, цены не
извлекаются.

Механика, общая с браузерным режимом B (кэш-пути, журнал, robots), живёт в
`parser._fetch_common`; здесь — политика режима A (троттлинг, ретраи).
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from parser._fetch_common import (
    RobotsGate,
    RobotsUnavailableError,
    append_fetch_log,
    normalize_host,
    read_cache,
    write_cache,
)

__all__ = [
    "AccessDeniedError",
    "PoliteClient",
    "USER_AGENT",
    "MAX_RETRIES",
    "BACKOFF_BASE_S",
    "normalize_host",
]

# Честный User-Agent с контактом (НЕ маскировка под браузер) — значение
# зафиксировано в ТЗ Phase 2, менять только вместе с ним.
USER_AGENT = (
    "proff58-catalog-parser/0.1 (+https://proff58.ru; contact: sktajem95@gmail.com) "
    "characteristics only, 1 req/3s, no images"
)

MAX_RETRIES = 3  # ретраев после первой попытки (итого до 4 обращений)
BACKOFF_BASE_S = 1.0  # возрастающая задержка ретраев: 1, 2, 3 с


class AccessDeniedError(Exception):
    """Доступ закрыт: 401/403, стойкий 429, запрет или недоступность robots.txt.

    Обходы не подбираем — при этом исключении источник пропускается.
    """


class PoliteClient:
    """Последовательный HTTP-клиент с троттлингом, кэшем и журналом доступа."""

    def __init__(
        self,
        cache_dir: Path,
        fetch_log_path: Path | None = None,
        throttle_s: float = 3.0,
        timeout_s: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._cache_dir = Path(cache_dir)
        self._fetch_log_path = Path(fetch_log_path) if fetch_log_path else None
        self._throttle_s = throttle_s
        self._last_request_at: dict[str, float] = {}
        self._robots_gate = RobotsGate(user_agent=USER_AGENT, fetcher=self._fetch_robots_text)
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_s,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def get_text(self, url: str) -> str:
        """Текст страницы: из дискового кэша, иначе по HTTP с ретраями."""
        cached = read_cache(self._cache_dir, url)
        if cached is not None:
            text, meta = cached
            self._log(
                url=url,
                final_url=meta.get("final_url", url),
                status=meta.get("status"),
                byte_count=len(text.encode("utf-8")),
                elapsed_s=0.0,
                throttle_wait_s=0.0,
                cache_hit=True,
            )
            return text

        self._check_robots(url)

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._request(url)
            except httpx.TransportError as exc:
                # сетевая ошибка — ретрай с backoff, как и 5xx
                last_error = exc
            else:
                status = response.status_code
                if status in (401, 403):
                    raise AccessDeniedError(
                        f"доступ запрещён (HTTP {status}), обходы не подбираем: {url}"
                    )
                if status == 429:
                    last_error = AccessDeniedError(
                        f"источник ограничил частоту (HTTP 429) "
                        f"после {MAX_RETRIES} ретраев: {url}"
                    )
                elif 500 <= status < 600:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {status}: {url}", request=response.request, response=response
                    )
                elif status >= 400:
                    # прочие 4xx (404 и т.п.) — без ретраев
                    response.raise_for_status()
                else:
                    self._write_cache(url, response)
                    return response.text
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE_S * (attempt + 1))
        raise last_error  # type: ignore[misc]

    # --- внутреннее ------------------------------------------------------

    def _request(self, url: str) -> httpx.Response:
        """Один HTTP-запрос с троттлингом по хосту и записью в журнал."""
        host = normalize_host(url)
        throttle_wait = self._throttle(host)
        started = time.monotonic()
        response = self._http.get(url)
        elapsed = time.monotonic() - started
        self._log(
            url=url,
            final_url=str(response.url),
            status=response.status_code,
            byte_count=len(response.content),
            elapsed_s=round(elapsed, 3),
            throttle_wait_s=round(throttle_wait, 3),
            cache_hit=False,
        )
        return response

    def _throttle(self, host: str) -> float:
        """Ждёт остаток паузы с прошлого запроса на хост; возвращает время сна."""
        now = time.monotonic()
        last = self._last_request_at.get(host)
        wait = 0.0
        if last is not None:
            wait = self._throttle_s - (now - last)
            if wait > 0:
                time.sleep(wait)
            else:
                wait = 0.0
        self._last_request_at[host] = time.monotonic()
        return wait

    def _check_robots(self, url: str) -> None:
        """Проверка robots.txt ДО запроса страницы; robots кэшируется на хост."""
        try:
            allowed = self._robots_gate.can_fetch(url)
        except RobotsUnavailableError as exc:
            # robots так и не получен — хост без robots НЕ обходим:
            # останавливаемся и докладываем (факт уходит в журнал фетчером)
            raise AccessDeniedError(
                f"robots.txt недоступен после {MAX_RETRIES + 1} попыток, "
                f"обход без robots запрещён: {exc}"
            ) from None
        if not allowed:
            self._log(
                url=url,
                final_url=None,
                status=None,
                byte_count=0,
                elapsed_s=0.0,
                throttle_wait_s=0.0,
                cache_hit=False,
                error="robots_disallow",
            )
            raise AccessDeniedError(f"robots.txt запрещает путь: {url}")

    def _fetch_robots_text(self, robots_url: str) -> str | None:
        """Текст robots.txt (фетчер для RobotsGate).

        200 — текст; 4xx — пустая строка (по конвенции ограничений нет);
        5xx/сетевая ошибка — ретрай (до MAX_RETRIES), при повторной неудаче —
        None: «ограничений нет» из недоступного robots не выводим (RFC 9309 —
        complete disallow), факт уходит в журнал как robots_unavailable.
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._request(robots_url)  # троттлинг действует и на robots
            except httpx.TransportError:
                # сетевая ошибка при получении robots — ретрай с backoff, как 5xx
                pass
            else:
                status = response.status_code
                if status == 200:
                    return response.text
                if 400 <= status < 500:
                    return ""
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE_S * (attempt + 1))
        self._log(
            url=robots_url,
            final_url=None,
            status=None,
            byte_count=0,
            elapsed_s=0.0,
            throttle_wait_s=0.0,
            cache_hit=False,
            error="robots_unavailable",
        )
        return None

    def _write_cache(self, url: str, response: httpx.Response) -> None:
        write_cache(
            self._cache_dir,
            url,
            text=response.text,
            final_url=str(response.url),
            status=response.status_code,
        )

    def _log(
        self,
        *,
        url: str,
        final_url: str | None,
        status: int | None,
        byte_count: int,
        elapsed_s: float,
        throttle_wait_s: float,
        cache_hit: bool,
        error: str | None = None,
    ) -> None:
        """Строка журнала доступа JSONL — артефакт приёмки троттлинга."""
        if self._fetch_log_path is None:
            return
        append_fetch_log(
            self._fetch_log_path,
            url=url,
            final_url=final_url,
            status=status,
            byte_count=byte_count,
            elapsed_s=elapsed_s,
            throttle_wait_s=throttle_wait_s,
            cache_hit=cache_hit,
            error=error,
        )
