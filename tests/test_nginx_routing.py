"""Регрессия маршрутизации nginx: BFF-эндпоинты → Next, Django-only → web.

Ловит дрейф, из-за которого browser-facing мутации кабинета уходили в Django
напрямую мимо Next-BFF и падали с «CSRF Failed: CSRF token missing» (у apiFetch
нет X-CSRFToken — его добавляет только BFF, lib/bff.ts). См. docker/nginx/default.conf.

Тест парсит РЕАЛЬНЫЙ конфиг и воспроизводит алгоритм выбора location nginx
(exact > самый длинный префикс > regex в порядке файла > префикс-fallback),
поэтому неверная правправка роутинга снова уронит именно эти проверки.
"""

import re
from pathlib import Path

import pytest

CONF = Path(__file__).resolve().parents[1] / "docker" / "nginx" / "default.conf"

# Пути, которые ОБЯЗАНЫ идти в Next (frontend:3000) — session/CSRF решает BFF.
FRONTEND_PATHS = [
    "/api/account/login/",
    "/api/account/logout/",
    "/api/account/me/",
    "/api/account/wishlist/",
    "/api/account/wishlist",
    # Карточки товаров избранного (#625): роут Next, хотя данные — каталожные.
    # Под /api/catalog/ он бы ушёл в Django и вернул 404 при зелёной сборке.
    "/api/account/wishlist/products",
    "/api/account/notifications/read-all/",
    "/api/account/notifications/preferences/",
    "/api/account/notifications/42/read/",
    "/api/account/max/link/",
    "/api/account/max/unlink/",
    "/api/account/max/status/",
    "/api/auth/max/start/",
    "/api/auth/max/abc123/status/",
    "/api/auth/max/abc123/cancel/",
    "/api/inquiry",
    "/api/cart",
    "/api/cart/items",
    "/api/cart/promo",
    "/api/cart/items/42",
    "/api/orders",
    "/api/orders/PROF-12",
    "/api/orders/PROF-12/",
    "/api/orders/PROF-12/invoice",
    "/api/orders/PROF-12/invoice/",
    "/api/orders/PROF-12/max-track/start",
    "/api/orders/max-track/xyz/status",
    "/api/catalog/products/drel/availability-subscription",
    "/api/search/suggest",
]

# Пути, которые ОБЯЗАНЫ оставаться на Django (web:8000).
WEB_PATHS = [
    "/api/catalog/categories/",
    "/api/catalog/products/drel/",
    "/api/catalog/products/drel/facets/",
    "/api/1c/products/import",  # интегратор 1С — только Django (X-Api-Key)
    "/api/1c/prices/update",
    "/api/orders/",  # список заказов (GET, безопасный метод) → Django
    "/api/ai/products/drel/recommendations/",
    "/healthz/",
    "/admin/",
]


def _upstream(body: str) -> str:
    """Апстрим location по телу блока."""
    if "alias" in body:
        return "static"
    if ":3000" in body:
        return "frontend"
    if ":8000" in body:
        return "web"
    return "other"


def _parse_locations(text: str):
    """Список (modifier, pattern, upstream) в порядке файла. Комментарии срезаны,
    чтобы прозаические упоминания 'location' в них не считались директивами."""
    text = re.sub(r"(?m)^\s*#.*$", "", text)
    locs = []
    for m in re.finditer(r"location\s+(=|~\*|~|\^~)?\s*(\S+)\s*\{([^}]*)\}", text):
        modifier, pattern, body = m.group(1), m.group(2), m.group(3)
        locs.append((modifier, pattern, _upstream(body)))
    return locs


def _match(uri: str, locs) -> str:
    """Выбор location как в nginx: = > самый длинный префикс (^~ прерывает) >
    regex в порядке файла > префикс-fallback."""
    for modifier, pattern, up in locs:
        if modifier == "=" and uri == pattern:
            return up
    best = None  # (pattern, upstream, modifier)
    for modifier, pattern, up in locs:
        if modifier in (None, "^~") and uri.startswith(pattern):
            if best is None or len(pattern) > len(best[0]):
                best = (pattern, up, modifier)
    if best and best[2] == "^~":
        return best[1]
    for modifier, pattern, up in locs:
        if modifier in ("~", "~*"):
            flags = re.IGNORECASE if modifier == "~*" else 0
            if re.search(pattern, uri, flags):
                return up
    return best[1] if best else None


@pytest.fixture(scope="module")
def locations():
    assert CONF.is_file(), f"конфиг не найден: {CONF}"
    locs = _parse_locations(CONF.read_text(encoding="utf-8"))
    assert locs, "не удалось распарсить location-блоки"
    return locs


@pytest.mark.parametrize("uri", FRONTEND_PATHS)
def test_bff_paths_go_to_next(uri, locations):
    assert (
        _match(uri, locations) == "frontend"
    ), f"{uri} должен идти в Next-BFF, иначе мутация упадёт с CSRF token missing"


@pytest.mark.parametrize("uri", WEB_PATHS)
def test_django_paths_stay_on_web(uri, locations):
    assert _match(uri, locations) == "web", f"{uri} должен оставаться на Django (web)"


def test_catchall_and_storefront(locations):
    # Прочий /api/ — в Django, витрина — в Next.
    assert _match("/api/something-new/", locations) == "web"
    assert _match("/", locations) == "frontend"
    assert _match("/catalog/perforatory", locations) == "frontend"


# --- Edge rate-limit API 1С (#439/m-04) ---


def test_onec_edge_zone_declared():
    text = CONF.read_text(encoding="utf-8")
    assert re.search(
        r"limit_req_zone\s+\$binary_remote_addr\s+zone=onec_edge:", text
    ), "нет limit_req_zone onec_edge — edge-лимит трафика 1С (m-04) не настроен"


def test_onec_edge_limit_applied_on_1c_location():
    # Отдельный location /api/1c/ обязан применять limit_req на зоне onec_edge.
    text = re.sub(r"(?m)^\s*#.*$", "", CONF.read_text(encoding="utf-8"))
    m = re.search(r"location\s+/api/1c/\s*\{([^}]*)\}", text)
    assert m, "нет отдельного location /api/1c/ с edge-лимитом"
    body = m.group(1)
    assert (
        "limit_req" in body and "onec_edge" in body
    ), "location /api/1c/ не применяет limit_req zone=onec_edge"


def test_1c_still_routes_to_django(locations):
    # Лимит не должен менять апстрим: обмен 1С по-прежнему на Django.
    assert _match("/api/1c/products/import", locations) == "web"
    assert _match("/api/1c/orders/new", locations) == "web"


def test_real_client_ip_recovered():
    # Без realip limit_req считал бы по IP docker-прокси (один бакет на всех).
    text = CONF.read_text(encoding="utf-8")
    assert "real_ip_header X-Forwarded-For" in text
    assert re.search(r"set_real_ip_from\s+\S+", text)
