#!/usr/bin/env python3
"""Smoke-проверка CSP-маршрутизации nginx для магазина «Профессионал» (#424, B-04).

Проверяет РАЗВЁРНУТЫЙ nginx (docker/nginx/default.conf): строгий
``default-src 'none'`` должен применяться ТОЛЬКО к JSON-маршрутам (``/api``,
``/healthz``), а витрина Next.js (HTML, ``/_next/*`` ассеты), админка и статика —
получать рабочую storefront-политику. Иначе server-level ``default-src 'none'``
блокирует JS/CSS/шрифты витрины (сломанный рендер, CSP violations).

Зависимостей нет — только стандартная библиотека. Read-only: скрипт лишь делает
GET-запросы и читает заголовки, ничего не пишет (в отличие от ``smoke_1c.py``),
поэтому безопасен и для prod.

Запуск:
    # из контейнера web против внутреннего nginx (как в deploy.yml):
    python scripts/smoke_csp.py --base http://nginx
    # против локального стека / staging:
    python scripts/smoke_csp.py --base http://localhost:8081
    python scripts/smoke_csp.py --base https://dev.proff58.ru --insecure

Коды возврата: 0 — все проверки прошли; 1 — хотя бы один провал.
"""

from __future__ import annotations

import argparse
import ssl
import sys
import urllib.error
import urllib.request

PASS, FAIL = "PASS", "FAIL"

# Маркеры политик из docker/nginx/default.conf (map $content_csp).
STRICT = "default-src 'none'"  # JSON API/healthz — исполнять как HTML/JS нельзя
STOREFRONT = "default-src 'self'"  # витрина/статика — рабочая политика


class Result:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        status = PASS if ok else FAIL
        if not ok:
            self.failed += 1
        line = f"[{status}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)


def fetch(base: str, path: str, ctx: ssl.SSLContext | None):
    """GET path на base; вернуть (status, csp) — csp приведён к нижнему регистру.

    add_header в nginx стоит с ``always``, поэтому CSP присутствует и на 4xx/5xx
    (напр. 502, если апстрим не поднят) — проверка политики не зависит от апстрима.
    """
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        status, headers = resp.status, resp.headers
        resp.read()  # дренируем тело
    except urllib.error.HTTPError as e:  # 4xx/5xx — заголовки нам всё равно нужны
        status, headers = e.code, e.headers
    csp = (headers.get("Content-Security-Policy") or "").lower()
    return status, csp


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke CSP-маршрутизации nginx (#424/B-04)")
    ap.add_argument("--base", default="http://localhost", help="базовый URL nginx")
    ap.add_argument("--insecure", action="store_true", help="не проверять TLS-сертификат")
    args = ap.parse_args()

    ctx: ssl.SSLContext | None = None
    if args.insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    print(f"CSP smoke → {args.base}")
    r = Result()

    # 1. Витрина: HTML отдаётся и НЕ под строгим 'none' (иначе Next.js сломан).
    st, csp = fetch(args.base, "/", ctx)
    r.check(st == 200, "GET / → 200 (витрина отвечает)", f"status={st}")
    r.check(STRICT not in csp, "GET / → CSP не строгий 'none'", csp or "(нет CSP)")
    r.check(STOREFRONT in csp, "GET / → storefront CSP (default-src 'self')", csp or "(нет CSP)")
    r.check(
        "script-src 'self'" in csp and "style-src 'self'" in csp,
        "GET / → script-src/style-src разрешены",
        csp or "(нет CSP)",
    )

    # 2. Ассеты Next.js: /_next/* не блокируются 'none' (статус может быть 404 —
    #    важна политика, а не наличие конкретного файла).
    _, csp_next = fetch(args.base, "/_next/static/smoke-check.css", ctx)
    r.check(STRICT not in csp_next, "GET /_next/* → не заблокировано 'none'", csp_next or "(нет CSP)")

    # 3. JSON API: строгий 'none' обязателен (браузер не исполняет как HTML/JS).
    st_api, csp_api = fetch(args.base, "/api/catalog/categories/", ctx)
    r.check(STRICT in csp_api, "GET /api/… → строгий 'none'", csp_api or "(нет CSP)")

    # 4. Healthcheck: тоже строгий 'none'.
    _, csp_hz = fetch(args.base, "/healthz/", ctx)
    r.check(STRICT in csp_hz, "GET /healthz/ → строгий 'none'", csp_hz or "(нет CSP)")

    print()
    if r.failed:
        print(f"РЕЗУЛЬТАТ: FAIL ({r.failed} провал(ов))")
        return 1
    print("РЕЗУЛЬТАТ: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
