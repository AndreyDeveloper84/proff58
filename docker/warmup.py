"""Прогрев web-воркеров после старта контейнера.

Запускается фоном из entrypoint перед gunicorn. Ждёт готовности gunicorn по
/healthz/, затем многократно дёргает публичные URL по внутреннему адресу, чтобы
КАЖДЫЙ воркер успел скомпилировать шаблоны и открыть соединение с БД до первого
живого клика (особенно после пересборки docker).

Важно: страницы витрины используют РАЗНЫЕ шаблоны — `/catalog/` рендерит
index.html, а страница категории `/catalog/<slug>/` — category.html (тяжёлый
view с фасетами). Поэтому греем и индекс, и реальную категорию, и каркас
админки (`/admin/login/` — публичен). Каждый URL бьём несколько раз (≈2×воркеров),
чтобы прогрелись все процессы gunicorn, а не только один.

Для не-healthz путей шлём X-Forwarded-Proto=https (иначе prod-настройка
SECURE_SSL_REDIRECT вернёт 301) и Host=localhost (точно в ALLOWED_HOSTS).
Прогрев не критичен — любые ошибки глушим, контейнер не валим.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request

BASE = "http://localhost:8000"
READY_ATTEMPTS = 60  # ~60 секунд ожидания готовности gunicorn


def _hit(path: str, *, secure: bool = False, timeout: float = 20.0) -> bool:
    req = urllib.request.Request(BASE + path)
    req.add_header("Host", "localhost")
    if secure:
        req.add_header("X-Forwarded-Proto", "https")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except Exception:
        return False


def _category_path() -> str | None:
    """URL верхнеуровневой категории витрины — чтобы прогреть шаблон category.html.

    Slug берём из БД через Django. Любая ошибка (нет категорий, БД недоступна) →
    None, тогда страницу категории просто не греем.
    """
    try:
        import django

        django.setup()
        from apps.catalog.models import Category

        slug = (
            Category.objects.filter(depth=1, is_active=True, on_site=True)
            .order_by("sort_order", "name")
            .values_list("slug", flat=True)
            .first()
        )
        return f"/catalog/{slug}/" if slug else None
    except Exception:
        return None


def main() -> int:
    # 1. Дождаться готовности gunicorn.
    for _ in range(READY_ATTEMPTS):
        if _hit("/healthz/"):
            break
        time.sleep(1)
    else:
        print("==> Прогрев пропущен: gunicorn не ответил вовремя", file=sys.stderr, flush=True)
        return 0

    # 2. URL для прогрева: витрина (index.html), страница категории (category.html),
    #    каркас админки (login.html). Все публичные, без авторизации.
    paths = ["/catalog/"]
    category = _category_path()
    if category:
        paths.append(category)
    paths.append("/admin/login/")

    # 3. Бьём каждый URL несколько раз, чтобы прогрелись все воркеры gunicorn
    #    (кэш скомпилированных шаблонов — per-process).
    workers = int(os.environ.get("GUNICORN_WORKERS", "3") or "3")
    repeat = max(2, workers * 2)
    for path in paths:
        for _ in range(repeat):
            _hit(path, secure=True)

    print(f"==> Прогрев выполнен ({len(paths)} URL x {repeat})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
