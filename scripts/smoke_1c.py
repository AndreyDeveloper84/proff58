#!/usr/bin/env python3
"""Smoke/contract-проверка живого 1С-API магазина «Профессионал».

Бьёт по эндпоинтам ``/api/1c/`` на указанном сервере (по умолчанию staging
``https://dev.proff58.ru``) и проверяет И happy-path, И ошибочные ответы
(403/400/404 + счётчики). Зависимостей нет — только стандартная библиотека,
запускается прямо из venv.

Заказы (#50) проверяются по факту реализации (orders/new → 200, orders/confirm
валидирует конверт и отдаёт per-item-результат), а не как заглушки 501.

ВНИМАНИЕ: скрипт ПИШЕТ в БД сервера — создаёт/обновляет тестовый товар
``SMOKE-1C-001`` (идемпотентно по ``code_1c``) и шлёт ``products/update`` для
несуществующего временного кода ``SMOKE-UPD-MISS-<unixtime>`` (товар не создаётся).
Гонять только против ТЕСТОВОГО контура (staging). Тестовый товар при желании
удалить в админке.

Запуск:
    python scripts/smoke_1c.py --base https://dev.proff58.ru --key <ONEC_API_KEY>
    ONEC_API_KEY=... python scripts/smoke_1c.py            # ключ из окружения
    python scripts/smoke_1c.py --key ... --insecure         # не проверять TLS-сертификат

Коды возврата: 0 — все проверки прошли (или режим без ключа: только auth-deny);
1 — хотя бы один провал.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

API_PREFIX = "/api/1c/"
DEFAULT_BASE = "https://dev.proff58.ru"
NOT_FOUND_CODE = "SMOKE-NOT-FOUND"

PASS, FAIL, SKIP, WARN = "PASS", "FAIL", "SKIP", "WARN"
_UNSET = object()


def _parse_body(raw: bytes):
    """Распарсить тело так же, как это делает 1С: сначала UTF-8, затем CP1251.

    Эндпоинты 1С отдают JSON в windows-1251 (``OneCJSONRenderer``), поэтому ответы
    с кириллицей (тексты ошибок, ``detail``) нельзя декодировать одним UTF-8 — иначе
    тело «ломается» в строку и проверки счётчиков/полей не видят dict.
    """
    if not raw:
        return None
    for enc in ("utf-8", "cp1251"):
        try:
            return json.loads(raw.decode(enc))
        except UnicodeDecodeError:
            continue
        except ValueError:
            # Декодировалось, но это не JSON — отдадим как текст в той же кодировке.
            return raw.decode(enc, "replace")
    return raw.decode("utf-8", "replace")


class OneCSmokeClient:
    """Тонкий HTTP-клиент 1С-API поверх stdlib urllib."""

    def __init__(
        self, base: str, key: str | None = None, insecure: bool = False, timeout: int = 30
    ):
        self.base = base.rstrip("/")
        self.key = key
        self.timeout = timeout
        self.ctx = ssl._create_unverified_context() if insecure else None

    def call(self, method, path, key=_UNSET, body=None, params=None):
        """Вернуть (status, parsed_body). status=0 — сетевая ошибка (detail в теле)."""
        url = self.base + API_PREFIX + path.lstrip("/")
        if params:
            url += "?" + urlencode(params)
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        # key=_UNSET → использовать self.key; key=None → явно без заголовка.
        use_key = self.key if key is _UNSET else key
        if use_key:
            headers["X-Api-Key"] = use_key
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
                return resp.status, _parse_body(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _parse_body(exc.read())
        except urllib.error.URLError as exc:
            return 0, f"network error: {exc.reason}"

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body, **kw):
        return self.call("POST", path, body=body, **kw)


class Runner:
    """Накапливает и печатает результаты проверок."""

    def __init__(self):
        self.results: list[tuple[str, str, str]] = []

    def record(self, name, status, detail=""):
        self.results.append((name, status, detail))
        mark = {PASS: "[PASS]", FAIL: "[FAIL]", SKIP: "[SKIP]", WARN: "[WARN]"}[status]
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    def check(self, name, cond, detail=""):
        self.record(name, PASS if cond else FAIL, detail)
        return cond

    def summary_exit_code(self) -> int:
        counts = {PASS: 0, FAIL: 0, SKIP: 0, WARN: 0}
        for _, status, _ in self.results:
            counts[status] += 1
        line = f"{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped"
        if counts[WARN]:
            line += f", {counts[WARN]} warn"
        print(f"\n=== {line} ===")
        return 1 if counts[FAIL] else 0


def _to_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _poll_sync(client: OneCSmokeClient, batch_uid: str, timeout: int = 40):
    """Опрашивать sync/<uid> с бэкоффом, пока finished. Вернуть dict или None при таймауте."""
    deadline = time.time() + timeout
    delay = 1.0
    while time.time() < deadline:
        status, body = client.get(f"sync/{batch_uid}")
        if status == 200 and isinstance(body, dict) and body.get("finished"):
            return body
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)
    return None


def _find_in_snapshot(client: OneCSmokeClient, code: str, max_pages: int = 20, limit: int = 1000):
    """Постранично искать code_1c в снимке. Вернуть row | None (нет) | 'TOO_MANY' (не нашли за лимит)."""
    offset = 0
    for _ in range(max_pages):
        status, body = client.get("snapshot/", params={"limit": limit, "offset": offset})
        if status != 200 or not isinstance(body, dict):
            return None
        for row in body.get("results", []):
            if row.get("code_1c") == code:
                return row
        nxt = body.get("next_offset")
        if nxt is None:
            return None
        offset = nxt
    return "TOO_MANY"


# --- Проверки без валидного ключа (выполняются всегда) ---


def check_auth_denied(r: Runner, client: OneCSmokeClient):
    status, _ = client.get("snapshot/", key=None)
    r.check("auth: без X-Api-Key → 403", status == 403, f"получено {status}")

    status, _ = client.get("snapshot/", key="wrong-key-smoke-xxxxx")
    r.check("auth: неверный X-Api-Key → 403", status == 403, f"получено {status}")


# --- Полный набор (нужен валидный ключ) ---


def check_snapshot_shape(r: Runner, client: OneCSmokeClient):
    status, body = client.get("snapshot/", params={"limit": 1})
    ok = status == 200 and isinstance(body, dict)
    keys = {"count", "limit", "offset", "next_offset", "results"}
    has_keys = ok and keys <= set(body)
    r.check(
        "snapshot: 200 + ключи count/limit/offset/next_offset/results",
        bool(has_keys),
        f"status={status}",
    )


def check_snapshot_validation(r: Runner, client: OneCSmokeClient):
    for query, label in (
        ({"limit": 0}, "limit=0"),
        ({"offset": -1}, "offset=-1"),
        ({"limit": "abc"}, "limit=abc"),
    ):
        status, _ = client.get("snapshot/", params=query)
        r.check(f"snapshot: {label} → 400", status == 400, f"получено {status}")

    status, body = client.get("snapshot/", params={"limit": 10_000_000})
    clamped = status == 200 and isinstance(body, dict) and body.get("limit", 10**9) <= 1000
    r.check(
        "snapshot: огромный limit → 200 и клампится ≤ ONEC_MAX_ITEMS",
        bool(clamped),
        f"status={status}, limit={body.get('limit') if isinstance(body, dict) else '—'}",
    )


def check_import_flow(r: Runner, client: OneCSmokeClient, code: str):
    bad = client.post("products/import", {"items": [{"name": "Без идентификатора"}]})
    r.check("products/import: без идентификатора → 400", bad[0] == 400, f"получено {bad[0]}")

    status, body = client.post(
        "products/import",
        {"items": [{"code_1c": code, "name": "Smoke Test 1C"}]},
    )
    accepted = (
        status == 202
        and isinstance(body, dict)
        and body.get("status") == "accepted"
        and body.get("batch_uid")
    )
    r.check("products/import: валидный item → 202 + batch_uid", bool(accepted), f"status={status}")
    if not accepted:
        return

    result = _poll_sync(client, body["batch_uid"])
    if result is None:
        r.record(
            "products/import: опрос sync до завершения",
            FAIL,
            "таймаут — проверьте, что контейнер celery на staging запущен",
        )
        return
    done = (
        result.get("status") in {"ok", "partial"}
        and (result.get("created", 0) + result.get("updated", 0)) >= 1
    )
    r.check(
        "products/import: sync finished, status ok/partial, created+updated≥1",
        bool(done),
        f"status={result.get('status')}, created={result.get('created')}, updated={result.get('updated')}",
    )


def check_sync_unknown(r: Runner, client: OneCSmokeClient):
    status, _ = client.get("sync/00000000-0000-0000-0000-000000000000")
    r.check("sync: неизвестный batch_uid → 404", status == 404, f"получено {status}")


def check_update_missing(r: Runner, client: OneCSmokeClient):
    code = f"SMOKE-UPD-MISS-{int(time.time())}"
    status, body = client.post("products/update", {"items": [{"code_1c": code, "name": "x"}]})
    accepted = status == 202 and isinstance(body, dict) and body.get("batch_uid")
    r.check("products/update: новый код → 202", bool(accepted), f"status={status}")
    if not accepted:
        return
    result = _poll_sync(client, body["batch_uid"])
    if result is None:
        r.record("products/update: опрос sync", FAIL, "таймаут (celery?)")
        return
    ok = result.get("skipped", 0) >= 1 and result.get("created", 0) == 0
    r.check(
        "products/update: несуществующий товар → skipped≥1, created==0",
        bool(ok),
        f"created={result.get('created')}, skipped={result.get('skipped')}",
    )


def check_prices(r: Runner, client: OneCSmokeClient, code: str, price: Decimal):
    bad = client.post("prices/update", {"items": [{"code_1c": code}]})
    r.check("prices/update: без price → 400", bad[0] == 400, f"получено {bad[0]}")

    status, body = client.post("prices/update", {"items": [{"code_1c": code, "price": str(price)}]})
    ok = status == 200 and isinstance(body, dict) and body.get("updated") == 1
    r.check(
        "prices/update: существующий код → 200, updated==1",
        bool(ok),
        f"status={status}, updated={body.get('updated') if isinstance(body, dict) else '—'}",
    )

    status, body = client.post(
        "prices/update", {"items": [{"code_1c": NOT_FOUND_CODE, "price": "9.99"}]}
    )
    nf = (
        status == 200
        and isinstance(body, dict)
        and body.get("updated") == 0
        and body.get("skipped") == 1
        and body.get("errors") == 0
    )
    r.check(
        "prices/update: несуществующий код → 200, updated==0, skipped==1, errors==0",
        bool(nf),
        f"status={status}, body={body}",
    )


def check_stocks(r: Runner, client: OneCSmokeClient, code: str, stock: Decimal, reserved: Decimal):
    bad = client.post("stocks/update", {"items": [{"code_1c": code}]})
    r.check("stocks/update: без полей остатка → 400", bad[0] == 400, f"получено {bad[0]}")

    status, body = client.post(
        "stocks/update",
        {"items": [{"code_1c": code, "stock": str(stock), "reserved": str(reserved)}]},
    )
    ok = status == 200 and isinstance(body, dict) and body.get("updated") == 1
    r.check(
        "stocks/update: существующий код → 200, updated==1",
        bool(ok),
        f"status={status}, updated={body.get('updated') if isinstance(body, dict) else '—'}",
    )

    status, body = client.post(
        "stocks/update", {"items": [{"code_1c": NOT_FOUND_CODE, "stock": "5"}]}
    )
    nf = (
        status == 200
        and isinstance(body, dict)
        and body.get("updated") == 0
        and body.get("skipped") == 1
    )
    r.check(
        "stocks/update: несуществующий код → 200, updated==0, skipped==1",
        bool(nf),
        f"status={status}, body={body}",
    )


def check_snapshot_reflects(
    r: Runner, client: OneCSmokeClient, code: str, price: Decimal, stock: Decimal, reserved: Decimal
):
    row = _find_in_snapshot(client, code)
    if row == "TOO_MANY":
        r.record(
            "snapshot: товар найден и значения сходятся",
            WARN,
            "товар не найден за лимит страниц (большой каталог) — проверьте вручную",
        )
        return
    if not row:
        r.check("snapshot: товар найден и значения сходятся", False, "товар не найден в снимке")
        return
    checks = {
        "price": _to_decimal(row.get("price")) == price,
        "stock": _to_decimal(row.get("stock")) == stock,
        "reserved": _to_decimal(row.get("reserved")) == reserved,
        "available": _to_decimal(row.get("available")) == (stock - reserved),
    }
    detail = ", ".join(f"{k}={'ok' if v else 'MISMATCH'}" for k, v in checks.items())
    r.check(
        "snapshot: price/stock/reserved/available сходятся (Decimal)",
        all(checks.values()),
        f"{detail}; row={row}",
    )


def check_orders_flow(r: Runner, client: OneCSmokeClient):
    """Реальная проверка обмена заказами (#50), контракт §5.6.

    Без сидинга заказов через HTTP: orders/new только читает (валидируем форму),
    orders/confirm проверяем на путях валидации и per-item-ошибке (неизвестный
    заказ → ``error`` в строке, а не 500). Создаётся служебный SyncLog(orders) —
    товаров/заказов не плодит.
    """
    # 1) orders/new — 200 + конверт {"items": [...]}; если заказы есть, проверяем форму строки.
    status, body = client.get("orders/new")
    shape_ok = status == 200 and isinstance(body, dict) and isinstance(body.get("items"), list)
    r.check("orders/new → 200 + items[]", bool(shape_ok), f"status={status}")
    if shape_ok and body["items"]:
        first = body["items"][0]
        keys = {"site_order_id", "order_number", "fulfillment_status", "payment", "items"}
        r.check(
            "orders/new: строка заказа содержит ключи контракта §5.6",
            keys <= set(first),
            f"keys={sorted(first)}",
        )

    # 2) orders/confirm — валидация конверта.
    empty = client.post("orders/confirm", {"items": []})
    r.check("orders/confirm: пустой items → 400", empty[0] == 400, f"получено {empty[0]}")

    no_id = client.post("orders/confirm", {"items": [{"onec_order_id": "1c-x"}]})
    r.check(
        "orders/confirm: строка без site_order_id/order_number → 400",
        no_id[0] == 400,
        f"получено {no_id[0]}",
    )

    # 3) orders/confirm — неизвестный заказ: 200 + per-item error (НЕ 500, НЕ откат батча).
    status, body = client.post(
        "orders/confirm",
        {"items": [{"site_order_id": 999_999_999, "onec_order_id": "1c-smoke-x"}]},
    )
    per_item = (
        status == 200
        and isinstance(body, dict)
        and body.get("items")
        and body["items"][0].get("status") == "error"
        and "batch_uid" in body
    )
    r.check(
        "orders/confirm: неизвестный заказ → 200, items[0].status=error, есть batch_uid",
        bool(per_item),
        f"status={status}, body={body}",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-проверка живого 1С-API.")
    parser.add_argument(
        "--base",
        default=os.environ.get("SMOKE_BASE", DEFAULT_BASE),
        help=f"базовый URL (по умолчанию {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("ONEC_API_KEY"),
        help="значение X-Api-Key (или env ONEC_API_KEY)",
    )
    parser.add_argument("--code", default="SMOKE-1C-001", help="code_1c тестового товара")
    parser.add_argument("--insecure", action="store_true", help="не проверять TLS-сертификат")
    parser.add_argument("--timeout", type=int, default=30, help="таймаут запроса, с")
    args = parser.parse_args(argv)

    print(f"Цель: {args.base}{API_PREFIX}  (товар {args.code})\n")
    client = OneCSmokeClient(args.base, key=args.key, insecure=args.insecure, timeout=args.timeout)
    runner = Runner()

    # Эти две проверки не требуют валидного ключа.
    check_auth_denied(runner, client)

    if not args.key:
        for name in (
            "snapshot/валидация",
            "snapshot/форма",
            "products/import",
            "sync/unknown",
            "products/update",
            "prices/update",
            "stocks/update",
            "snapshot/после записи",
            "orders",
        ):
            runner.record(f"[нужен --key] {name}", SKIP, "передайте --key или env ONEC_API_KEY")
        return runner.summary_exit_code()

    # Цена меняется между запусками: иначе при повторном smoke цена не отличается
    # от текущей и идёт в skipped (идемпотентность #111), а не updated.
    price = Decimal(f"{1000 + int(time.time()) % 9000}.{int(time.time() * 100) % 100:02d}")
    stock = Decimal("10.000")
    reserved = Decimal("3.000")

    check_snapshot_shape(runner, client)
    check_snapshot_validation(runner, client)
    check_import_flow(runner, client, args.code)
    check_sync_unknown(runner, client)
    check_update_missing(runner, client)
    check_prices(runner, client, args.code, price)
    check_stocks(runner, client, args.code, stock, reserved)
    check_snapshot_reflects(runner, client, args.code, price, stock, reserved)
    check_orders_flow(runner, client)

    return runner.summary_exit_code()


if __name__ == "__main__":
    sys.exit(main())
