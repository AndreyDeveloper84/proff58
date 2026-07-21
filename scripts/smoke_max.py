#!/usr/bin/env python3
"""Smoke-проверка MAX-бота — валидность токена и webhook подписки.

Зависимостей нет — только стандартная библиотека. Проверяет:
- GET /me — токен валиден, бот отвечает
- GET /subscriptions — webhook подписан
- Опционально: POST /subscriptions — подписка на webhook

Запуск:
    python scripts/smoke_max.py --token <BOT_TOKEN>
    MAX_BOT_TOKEN=... python scripts/smoke_max.py
    python scripts/smoke_max.py --token ... --subscribe https://proff58.ru/api/max/webhook/
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("MAX_BOT_API_URL", "https://platform-api2.max.ru").rstrip("/")

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _request(method, path, token, body=None, insecure=False):
    url = f"{API_BASE}/{path.lstrip('/')}"
    headers = {"Authorization": token, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": str(exc)}
        return exc.code, body
    except Exception as exc:
        return 0, {"error": str(exc)}


class Runner:
    def __init__(self):
        self.results = []

    def check(self, name, cond, detail=""):
        status = PASS if cond else FAIL
        self.results.append((name, status))
        mark = "[PASS]" if cond else "[FAIL]"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
        return cond

    def skip(self, name, detail=""):
        self.results.append((name, SKIP))
        print(f"[SKIP] {name}" + (f" — {detail}" if detail else ""))

    def summary(self):
        p = sum(1 for _, s in self.results if s == PASS)
        f = sum(1 for _, s in self.results if s == FAIL)
        s = sum(1 for _, s in self.results if s == SKIP)
        print(f"\n=== {p} passed, {f} failed, {s} skipped ===")
        return 1 if f else 0


def check_bot_info(r, token, insecure):
    status, body = _request("GET", "/me", token, insecure=insecure)
    ok = status == 200 and isinstance(body, dict) and body.get("is_bot") is True
    r.check(
        "GET /me — токен валиден, бот найден",
        ok,
        f"name={body.get('name')}, username={body.get('username')}" if ok else f"status={status}",
    )
    return ok


def check_subscriptions(r, token, insecure):
    status, body = _request("GET", "/subscriptions", token, insecure=insecure)
    ok = status == 200 and isinstance(body, dict)
    if not ok:
        r.check("GET /subscriptions — список подписок", False, f"status={status}")
        return

    subs = body.get("subscriptions", [])
    if subs:
        urls = [s.get("url", "?") for s in subs]
        r.check("GET /subscriptions — есть активные подписки", True, f"urls={urls}")
    else:
        r.check(
            "GET /subscriptions — есть активные подписки",
            False,
            "нет подписок; используйте --subscribe <url>",
        )


def subscribe_webhook(r, token, url, secret, insecure):
    if not secret:
        r.check(
            f"POST /subscriptions — подписка на {url}",
            False,
            "укажите --secret или MAX_WEBHOOK_SECRET",
        )
        return

    status, body = _request(
        "POST",
        "/subscriptions",
        token,
        body={
            "url": url,
            "secret": secret,
            "update_types": [
                "bot_started",
                "message_created",
                "message_callback",
            ],
        },
        insecure=insecure,
    )
    ok = status == 200
    r.check(
        f"POST /subscriptions — подписка на {url}",
        ok,
        f"status={status}, body={body}" if not ok else "подписка создана",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smoke-проверка MAX-бота.")
    parser.add_argument(
        "--token",
        default=os.environ.get("MAX_BOT_TOKEN"),
        help="токен бота (или env MAX_BOT_TOKEN)",
    )
    parser.add_argument(
        "--subscribe",
        metavar="URL",
        help="подписать webhook (напр. https://proff58.ru/api/max/webhook/)",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("MAX_WEBHOOK_SECRET"),
        help="секрет webhook (или env MAX_WEBHOOK_SECRET; обязателен с --subscribe)",
    )
    parser.add_argument("--insecure", action="store_true", help="не проверять TLS")
    args = parser.parse_args(argv)

    if not args.token:
        print("Ошибка: укажите --token или задайте MAX_BOT_TOKEN в окружении.")
        return 1

    print(f"Цель: {API_BASE}\n")
    r = Runner()

    bot_ok = check_bot_info(r, args.token, args.insecure)
    if not bot_ok:
        print("\nТокен невалиден — дальнейшие проверки невозможны.")
        return r.summary()

    if args.subscribe:
        subscribe_webhook(r, args.token, args.subscribe, args.secret, args.insecure)

    check_subscriptions(r, args.token, args.insecure)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
