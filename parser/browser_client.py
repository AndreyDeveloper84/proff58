"""Браузерный клиент режима B: добор карточек с закрытых источников.

Для источников, отвечающих на HTTP 403/401 (`vseinstrumenti.ru`,
`dns-shop.ru`), страницы забираются через Playwright (chromium) с persistent
context + `storage_state`: профиль и куки живут между запусками. Первый
запуск — разовый headed-bootstrap, челлендж проходит ЧЕЛОВЕК, сессия
сохраняется; дальше — headless на сохранённой сессии. Автоматического
решения капчи нет — ни своими силами, ни внешними сервисами.

Жёсткие правила режима B (ТЗ «ДВА РЕЖИМА ДОБЫЧИ»):

- человеческий темп: случайная пауза 5–10 с между карточками, никакого
  параллелизма, лимит карточек за прогон (по умолчанию 100); лимит считает
  только карточки — запросы фазы сбора URL (sitemap/листинг) его не тратят;
- при 403/429 или маркерах челленджа в HTML — `BrowserChallengeError`,
  СТОП и доклад в stderr. Никаких «подождать и повторить»: сработала
  защита → профиль неверен → решение владельца;
- фотографии не берём: загрузка image/media/font режется route abort;
- кэш страниц, журнал JSONL и robots.txt — общие с режимом A
  (`parser._fetch_common`); сам robots получается один раз через httpx
  (один лёгкий запрос, не карточка).

Интерфейс совместим с `PoliteClient`: `get_text(url) -> str`, `close()`.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from parser._fetch_common import (
    RobotsGate,
    RobotsUnavailableError,
    append_fetch_log,
    read_cache,
    write_cache,
)
from parser.client import AccessDeniedError

# User-Agent реального Chrome: в режиме B мы и есть браузер человека
# (headed-bootstrap проходит владелец), маскировки под «другой» браузер нет.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_PROFILE_DIR = Path("scratchpad/parser-mvp/browser-profile")
DEFAULT_PACE_S = (5.0, 10.0)
DEFAULT_RUN_LIMIT = 100
ROBOTS_TIMEOUT_S = 10.0

# HTTP-статусы сработавшей защиты — стоп без единого ретрая.
CHALLENGE_STATUSES = (403, 429)

# Маркеры челленджа/капчи в HTML (сравнение в нижнем регистре, ё → е).
CHALLENGE_MARKERS = (
    "доступ запрещен",
    "captcha",
    "challenge-platform",
    "подтвердите, что вы не робот",
)

# Тяжёлые ресурсы не загружаем: фотографии не берём и в этом режиме тоже.
BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})


class BrowserChallengeError(AccessDeniedError):
    """Защита источника сработала: 403/429 или челлендж в HTML.

    Наследник AccessDeniedError, чтобы прогон останавливался тем же путём,
    что и отказ доступа в режиме A (доклад + частичная запись результатов).
    """


class BrowserRunLimitError(Exception):
    """Исчерпан лимит карточек на прогон — плановая остановка, не ошибка сайта.

    НЕ наследник AccessDeniedError: лимит — не отказ доступа. Прогон
    завершается штатно: частичные результаты записываются, exit code 0.
    """


def find_challenge_marker(html: str) -> str | None:
    """Маркер челленджа в HTML или None (сравнение в lower, ё → е)."""
    lowered = html.lower().replace("ё", "е")
    for marker in CHALLENGE_MARKERS:
        if marker in lowered:
            return marker
    return None


def abort_heavy_resources(route, request) -> None:
    """Route-обработчик: image/media/font режем, остальное пропускаем."""
    if request.resource_type in BLOCKED_RESOURCE_TYPES:
        route.abort()
    else:
        route.continue_()


class BrowserClient:
    """Последовательный браузерный клиент: темп, лимит прогона, стоп на челлендже.

    Параметры:
        cache_dir: дисковый кэш страниц (формат общий с режимом A);
        fetch_log_path: журнал доступа JSONL (+ поле mode="browser");
        profile_dir: каталог persistent context; storage_state — рядом
            (`<profile_dir>.storage-state.json`);
        pace_s: (min, max) случайной паузы между карточками, секунды;
        run_limit: максимум карточек за прогон (BrowserRunLimitError сверху);
        headless: False — видимое окно (только bootstrap с человеком);
        launcher: DI для тестов — фабрика фейкового context вместо playwright;
        robots_fetcher: DI для тестов — фетчер текста robots.txt.
    """

    def __init__(
        self,
        *,
        cache_dir: Path,
        fetch_log_path: Path | None = None,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        pace_s: tuple[float, float] = DEFAULT_PACE_S,
        run_limit: int = DEFAULT_RUN_LIMIT,
        headless: bool = True,
        launcher: Callable[[], object] | None = None,
        robots_fetcher: Callable[[str], str | None] | None = None,
    ):
        self._cache_dir = Path(cache_dir)
        self._fetch_log_path = Path(fetch_log_path) if fetch_log_path else None
        self._profile_dir = Path(profile_dir)
        self._storage_state_path = self._profile_dir.with_name(
            self._profile_dir.name + ".storage-state.json"
        )
        self._pace_s = pace_s
        self._run_limit = run_limit
        self._headless = headless
        self._launcher = launcher
        self._robots_fetcher = robots_fetcher
        self._robots_gate = RobotsGate(
            user_agent=BROWSER_USER_AGENT, fetcher=self._fetch_robots_text
        )
        self._playwright = None
        self._context = None
        self._fetched = 0  # карточек, реально сходивших в браузер за прогон
        # лимит считает только карточки: sitemap/листинг идут до start_card_phase()
        self._card_phase = False

    def start_card_phase(self) -> None:
        """Переход к фазе карточек: лимит прогона считает только карточки.

        Вызывается оркестратором между сбором URL (sitemap/листинг) и циклом
        карточек: запросы фазы сбора в браузер ходят, но лимит не тратят.
        """
        self._card_phase = True

    def close(self) -> None:
        """Сохранить storage_state и закрыть context/playwright (идемпотентно)."""
        if self._context is not None:
            try:
                self._context.storage_state(path=str(self._storage_state_path))
            except Exception:
                pass  # context мог быть уже закрыт (например, окно закрыл человек)
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self) -> BrowserClient:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def get_text(self, url: str) -> str:
        """Текст страницы: из дискового кэша, иначе через браузер.

        До браузера: кэш → лимит прогона (только в фазе карточек) → robots.
        Челлендж (403/429 или маркеры в HTML) — BrowserChallengeError без
        единого ретрая. В кэш пишется только успешный ответ (HTTP 200).
        """
        cached = read_cache(self._cache_dir, url)
        if cached is not None:
            text, meta = cached
            self._log(
                url=url,
                final_url=meta.get("final_url", url),
                status=meta.get("status"),
                byte_count=len(text.encode("utf-8")),
                elapsed_s=0.0,
                pace_wait_s=0.0,
                cache_hit=True,
            )
            return text

        # лимит — до robots: после исчерпания лимита лишний запрос за
        # robots.txt не уходит; вне фазы карточек лимит не действует
        if self._card_phase and self._fetched >= self._run_limit:
            raise BrowserRunLimitError(
                f"исчерпан лимит {self._run_limit} карточек на прогон, "
                f"остановка по плану: {url}"
            )
        self._check_robots(url)

        context = self._ensure_context()
        pace_wait = self._pace()
        started = time.monotonic()
        page = context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            status = response.status if response is not None else None
            html = page.content()
            final_url = page.url
        finally:
            page.close()
        if self._card_phase:
            self._fetched += 1
        elapsed = time.monotonic() - started

        marker = find_challenge_marker(html) if status not in CHALLENGE_STATUSES else None
        if status in CHALLENGE_STATUSES or marker is not None:
            reason = f"HTTP {status}" if status in CHALLENGE_STATUSES else f"маркер {marker!r}"
            self._log(
                url=url,
                final_url=final_url,
                status=status,
                byte_count=len(html.encode("utf-8")),
                elapsed_s=round(elapsed, 3),
                pace_wait_s=round(pace_wait, 3),
                cache_hit=False,
                error="challenge",
            )
            message = (
                f"защита источника сработала ({reason}): {url} — прогон "
                f"остановлен без повторов; сессию обновляет владелец (bootstrap)"
            )
            print(f"СТОП: {message}", file=sys.stderr)
            raise BrowserChallengeError(message)

        # кэшируем только успешный ответ (как режим A): 404/500 не должны
        # застревать в кэше навсегда — при следующем прогоне запрос повторится
        if status == 200:
            write_cache(self._cache_dir, url, text=html, final_url=final_url, status=status)
        self._log(
            url=url,
            final_url=final_url,
            status=status,
            byte_count=len(html.encode("utf-8")),
            elapsed_s=round(elapsed, 3),
            pace_wait_s=round(pace_wait, 3),
            cache_hit=False,
        )
        return html

    def bootstrap(self) -> None:
        """Разовый headed-запуск: человек проходит челлендж, сессия сохраняется.

        Открывает видимое окно (headless=False задаётся при создании клиента)
        и ждёт Enter: владелец переходит на сайт источника, проходит проверку
        вручную, возвращается в консоль — close() сохраняет storage_state.
        """
        context = self._ensure_context()
        page = context.new_page()
        try:
            page.goto("about:blank")
            print(
                "Bootstrap сессии: в открывшемся окне браузера перейдите на сайт "
                "источника и пройдите проверку вручную (автоматического решения "
                "капчи нет и не будет).",
                file=sys.stderr,
            )
            try:
                input("Нажмите Enter, когда проверка пройдена — сессия сохранится: ")
            except EOFError:
                pass  # неинтерактивный запуск: сессия всё равно сохранится при close()
        finally:
            page.close()
        self.close()
        print(f"Сессия сохранена: {self._storage_state_path}", file=sys.stderr)

    # --- внутреннее ------------------------------------------------------

    def _ensure_context(self):
        """Persistent context (лениво) + route abort + storage_state куки."""
        if self._context is None:
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            launcher = self._launcher or self._default_launcher
            context = launcher()
            context.route("**/*", abort_heavy_resources)
            self._load_storage_state(context)
            self._context = context
        return self._context

    def _default_launcher(self):
        """Производственный запуск playwright (импорт ленивый: нужен только здесь)."""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        return self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            headless=self._headless,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 768},
            user_agent=BROWSER_USER_AGENT,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--lang=ru-RU,ru",
            ],
        )

    def _load_storage_state(self, context) -> None:
        """Куки из storage_state прошлого запуска (по паттерну wb_p)."""
        if not self._storage_state_path.exists():
            return
        state = json.loads(self._storage_state_path.read_text(encoding="utf-8"))
        cookies = state.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)

    def _pace(self) -> float:
        """Случайная пауза pace_s между карточками; возвращает время сна.

        Перед первой карточкой прогона паузы нет.
        """
        if self._fetched == 0:
            return 0.0
        wait = random.uniform(*self._pace_s)
        time.sleep(wait)
        return wait

    def _check_robots(self, url: str) -> None:
        """Проверка robots.txt ДО захода в браузер; robots кэшируется на хост."""
        try:
            allowed = self._robots_gate.can_fetch(url)
        except RobotsUnavailableError as exc:
            raise AccessDeniedError(
                f"robots.txt недоступен, обход без robots запрещён: {exc}"
            ) from None
        if not allowed:
            self._log(
                url=url,
                final_url=None,
                status=None,
                byte_count=0,
                elapsed_s=0.0,
                pace_wait_s=0.0,
                cache_hit=False,
                error="robots_disallow",
            )
            raise AccessDeniedError(f"robots.txt запрещает путь: {url}")

    def _fetch_robots_text(self, robots_url: str) -> str | None:
        """Текст robots.txt одним лёгким httpx-запросом (не карточка, без темпа).

        200 — текст; 4xx — пустая строка (ограничений нет); 5xx/сетевая
        ошибка — None (обход без robots запрещён). Без ретраев.
        """
        if self._robots_fetcher is not None:
            return self._robots_fetcher(robots_url)
        try:
            response = httpx.get(
                robots_url,
                headers={"User-Agent": BROWSER_USER_AGENT},
                timeout=ROBOTS_TIMEOUT_S,
                follow_redirects=True,
            )
        except httpx.HTTPError:
            return None
        self._log(
            url=robots_url,
            final_url=str(response.url),
            status=response.status_code,
            byte_count=len(response.content),
            elapsed_s=round(response.elapsed.total_seconds(), 3),
            pace_wait_s=0.0,
            cache_hit=False,
        )
        if response.status_code == 200:
            return response.text
        if 400 <= response.status_code < 500:
            return ""
        return None

    def _log(
        self,
        *,
        url: str,
        final_url: str | None,
        status: int | None,
        byte_count: int,
        elapsed_s: float,
        pace_wait_s: float,
        cache_hit: bool,
        error: str | None = None,
    ) -> None:
        """Строка журнала JSONL тем же форматом, что у режима A (+ mode)."""
        if self._fetch_log_path is None:
            return
        append_fetch_log(
            self._fetch_log_path,
            url=url,
            final_url=final_url,
            status=status,
            byte_count=byte_count,
            elapsed_s=elapsed_s,
            throttle_wait_s=pace_wait_s,  # поле формата режима A = пауза темпа
            cache_hit=cache_hit,
            error=error,
            extra={"mode": "browser"},
        )
