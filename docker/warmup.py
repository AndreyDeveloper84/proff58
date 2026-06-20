"""Прогрев web-воркеров после старта контейнера.

Запускается фоном из entrypoint перед gunicorn. Ждёт готовности gunicorn по
/healthz/, затем дёргает публичные URL, чтобы ПЕРВЫЙ живой запрос (особенно
после пересборки) не ловил установку соединения с БД и ленивую компиляцию
шаблонов. Прогрев идёт по внутреннему адресу; для /catalog/ шлём
X-Forwarded-Proto=https, иначе prod-настройка SECURE_SSL_REDIRECT вернёт 301 и
вью не выполнится. Прогрев не критичен — любые ошибки глушим, контейнер не валим.
"""

from __future__ import annotations

import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
# Публичные страницы, разделяющие максимум кода с админкой (ORM, шаблонный движок,
# соединение с БД). Админку прогреть нельзя — нужна авторизация.
WARMUP_PATHS = ("/catalog/",)
READY_ATTEMPTS = 60  # ~60 секунд ожидания готовности gunicorn


def _hit(path: str, *, secure: bool = False, timeout: float = 15.0) -> bool:
    req = urllib.request.Request(BASE + path)
    if secure:
        req.add_header("X-Forwarded-Proto", "https")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except Exception:
        return False


def main() -> int:
    for _ in range(READY_ATTEMPTS):
        if _hit("/healthz/"):
            for path in WARMUP_PATHS:
                _hit(path, secure=True)
            print("==> Прогрев выполнен", flush=True)
            return 0
        time.sleep(1)
    print("==> Прогрев пропущен: gunicorn не ответил вовремя", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
