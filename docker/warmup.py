"""Прогрев web-воркеров после старта контейнера.

Запускается фоном из entrypoint перед gunicorn. Ждёт готовности gunicorn по
/healthz/, затем многократно дёргает публичные URL по внутреннему адресу, чтобы
КАЖДЫЙ воркер успел скомпилировать шаблоны и открыть соединение с БД до первого
живого клика (особенно после пересборки docker).

Что греем:
- шаблоны (кэш компиляции — per-process): индекс index.html, страница категории
  category.html и каркас админки `/admin/login/` — каждый repeat≈2×воркеров раз,
  чтобы прогрелись ВСЕ процессы gunicorn, а не один;
- данные: все верхнеуровневые категории по одному разу — чтобы их строки попали в
  кэш PostgreSQL (он общий для воркеров) и первый клик по большому разделу не читал
  данные с диска (особенно на HDD это давало 20–30 с на первом обращении).

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


def _category_paths() -> list[str]:
    """URL всех верхнеуровневых категорий витрины.

    Нужны, чтобы прогреть шаблон category.html и подтянуть строки каждой категории
    в кэш PostgreSQL (тогда первый живой клик по большому разделу не читает данные
    с диска). Slug берём из БД через Django. Любая ошибка (нет категорий, БД
    недоступна) → пустой список, тогда категории просто не греем.
    """
    try:
        import django

        # Запуск как `python /app/docker/warmup.py` кладёт в sys.path каталог скрипта
        # (/app/docker), а не корень проекта (/app) — добавим его, иначе `import apps...`
        # упадёт и категории не прогреются.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        django.setup()
        from apps.catalog.models import Category

        slugs = (
            Category.objects.filter(depth=1, is_active=True, on_site=True)
            .order_by("sort_order", "name")
            .values_list("slug", flat=True)
        )
        return [f"/catalog/{slug}/" for slug in slugs]
    except Exception:
        return []


def main() -> int:
    # 1. Дождаться готовности gunicorn.
    for _ in range(READY_ATTEMPTS):
        if _hit("/healthz/"):
            break
        time.sleep(1)
    else:
        print("==> Прогрев пропущен: gunicorn не ответил вовремя", file=sys.stderr, flush=True)
        return 0

    workers = int(os.environ.get("GUNICORN_WORKERS", "3") or "3")
    repeat = max(2, workers * 2)
    categories = _category_paths()

    # 2. Прогрев ШАБЛОНОВ на всех воркерах (кэш скомпилированных шаблонов — per-process):
    #    индекс (index.html), одна категория (category.html), каркас админки (login.html).
    #    repeat раз, чтобы запросы разошлись по всем процессам gunicorn.
    template_paths = ["/catalog/"]
    if categories:
        template_paths.append(categories[0])
    template_paths.append("/admin/login/")
    for path in template_paths:
        for _ in range(repeat):
            _hit(path, secure=True)

    # 3. Прогрев ДАННЫХ: остальные категории по одному разу — чтобы их строки попали
    #    в кэш PostgreSQL (он общий для всех воркеров), и первый клик по любому разделу
    #    не читал большую категорию с диска. Одного запроса достаточно: кэш БД — серверный.
    for path in categories[1:]:
        _hit(path, secure=True)

    print(
        f"==> Прогрев выполнен (шаблоны: {len(template_paths)} x {repeat}, "
        f"категорий: {len(categories)})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
