"""Клиент API СДЭК v2 (DRF-2299).

Только транспорт: авторизация, справочники городов и пунктов выдачи, расчёт тарифа,
создание и чтение заказа. Бизнес-решения (какой тариф, что считать ошибкой расчёта
для покупателя) — в ``apps.delivery`` и ``apps.integration_ship.services``.

Контур задаётся ``CDEK_API_URL``: по умолчанию тестовый ``api.edu.cdek.ru``. Для него
СДЭК публикует общие тестовые ключи — они подставляются, только если свои не заданы и
URL тестовый. С боевым URL без ключей клиент недоступен (``is_configured() is False``).

Токен живёт в кеше Django до истечения минус минута. В логах — только метод, путь,
HTTP-код и код ошибки СДЭК, без токена, адресов и телефонов.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache

from ..ports import Parcel

logger = logging.getLogger(__name__)

TEST_API_URL = "https://api.edu.cdek.ru/v2"
# Публичные ключи тестового контура из документации СДЭК — только для TEST_API_URL.
TEST_ACCOUNT = "wqGwiQx0gg8mLtiEKsUinjVSICCjtTEP"
TEST_SECURE = "RmAmgvSgSl1yirlz9QupbzOJVqhCxcP5"

_TOKEN_CACHE_KEY = "cdek:oauth-token:{account}"
# Пока стоит этот ключ, запросы к СДЭК не отправляются: после сбоя сети или 5xx не
# держим потоки сайта на таймаутах каждого посетителя.
_DOWN_KEY = "cdek:down"
_DOWN_TTL = 60


class CdekError(RuntimeError):
    """Ошибка обращения к СДЭК.

    ``retryable`` — сеть, таймаут, 429/5xx, непонятный ответ: СДЭК временно недоступен.
    ``auth`` — ключи не заданы или отвергнуты (401/403): это поломка настройки, а не
    «такой доставки нет», и о ней надо кричать в лог.
    """

    def __init__(
        self, message: str, *, retryable: bool, status: int | None = None, auth: bool = False
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.auth = auth


def _package(parcel: Parcel) -> dict:
    return {
        "weight": parcel.weight_g,
        "length": parcel.length_cm,
        "width": parcel.width_cm,
        "height": parcel.height_cm,
    }


@dataclass(frozen=True)
class Tariff:
    code: int
    name: str
    delivery_mode: int
    cost: Decimal
    period_min: int = 0
    period_max: int = 0


@dataclass(frozen=True)
class City:
    code: int
    name: str
    full_name: str


@dataclass(frozen=True)
class DeliveryPoint:
    code: str
    name: str
    address: str
    work_time: str = ""
    latitude: float | None = None
    longitude: float | None = None
    weight_max_kg: int | None = None


def _base_url() -> str:
    return (getattr(settings, "CDEK_API_URL", "") or TEST_API_URL).rstrip("/")


def _credentials() -> tuple[str, str]:
    account = getattr(settings, "CDEK_ACCOUNT", "") or ""
    secure = getattr(settings, "CDEK_SECURE", "") or ""
    if not account and _base_url() == TEST_API_URL:
        return TEST_ACCOUNT, TEST_SECURE
    return account, secure


def is_configured() -> bool:
    account, secure = _credentials()
    return bool(account and secure)


def _timeout() -> tuple[float, float]:
    """(соединение, чтение): недоступный хост отваливается за секунды."""
    return (
        float(getattr(settings, "CDEK_CONNECT_TIMEOUT", 3)),
        float(getattr(settings, "CDEK_TIMEOUT", 7)),
    )


def _cache_get(key):
    try:
        return cache.get(key)
    except Exception:  # noqa: BLE001 — кеш вспомогательный, без него просто дольше
        return None


def _cache_set(key, value, ttl) -> None:
    try:
        cache.set(key, value, ttl)
    except Exception:  # noqa: BLE001
        pass


def _cache_delete(key) -> None:
    try:
        cache.delete(key)
    except Exception:  # noqa: BLE001
        pass


def _unavailable(reason: str, *, status: int | None = None) -> CdekError:
    """СДЭК недоступен: пометить на минуту, чтобы следующие запросы не ждали таймаут."""
    _cache_set(_DOWN_KEY, 1, _DOWN_TTL)
    return CdekError(f"СДЭК недоступен: {reason}", retryable=True, status=status)


def _classify(response: requests.Response) -> CdekError:
    status = response.status_code
    codes = ""
    try:
        body = response.json()
        errors = body.get("errors") or body.get("requests", [{}])[0].get("errors") or []
        codes = ",".join(str(e.get("code", "")) for e in errors if isinstance(e, dict))
    except (ValueError, AttributeError, IndexError, TypeError):
        pass
    message = f"СДЭК HTTP {status} {codes}".strip()
    if status == 429 or status >= 500:
        return _unavailable(message, status=status)
    return CdekError(message, retryable=False, status=status, auth=status in (401, 403))


def _json(response: requests.Response):
    try:
        return response.json()
    except ValueError:
        raise _unavailable(f"не JSON в ответе (HTTP {response.status_code})") from None


def _fetch_token() -> str:
    account, secure = _credentials()
    if not (account and secure):
        raise CdekError("Ключи СДЭК не заданы", retryable=False, auth=True)
    key = _TOKEN_CACHE_KEY.format(account=account)
    token = _cache_get(key)
    if token:
        return token
    try:
        response = requests.post(
            f"{_base_url()}/oauth/token",
            params={
                "grant_type": "client_credentials",
                "client_id": account,
                "client_secret": secure,
            },
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        raise _unavailable(type(exc).__name__) from exc
    if response.status_code != 200:
        error = _classify(response)
        if response.status_code in (400, 401, 403):
            # Неверные ключи СДЭК отвечает 400/401 на выдаче токена.
            error.auth = True
        raise error
    data = _json(response)
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        raise _unavailable("нет access_token в ответе")
    try:
        ttl = max(int(data.get("expires_in", 3600)) - 60, 60)
    except (TypeError, ValueError):
        ttl = 60
    _cache_set(key, token, ttl)
    return token


def _drop_token() -> None:
    account, _ = _credentials()
    _cache_delete(_TOKEN_CACHE_KEY.format(account=account))


def _request(method: str, path: str, *, params=None, json=None, _retry_auth: bool = True):
    if _cache_get(_DOWN_KEY):
        raise CdekError("СДЭК недоступен (пауза после сбоя)", retryable=True)
    token = _fetch_token()
    try:
        response = requests.request(
            method,
            f"{_base_url()}{path}",
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        logger.warning("CDEK %s %s: %s", method, path, type(exc).__name__)
        raise _unavailable(type(exc).__name__) from exc
    if response.status_code == 401 and _retry_auth:
        # Токен отозван раньше срока — один раз берём новый.
        _drop_token()
        return _request(method, path, params=params, json=json, _retry_auth=False)
    if response.status_code >= 400:
        error = _classify(response)
        logger.warning("CDEK %s %s: %s", method, path, error)
        raise error
    return _json(response)


# ── справочники ───────────────────────────────────────────────────────────


def suggest_cities(query: str, *, limit: int = 10) -> list[City]:
    query = (query or "").strip()
    if len(query) < 2:
        return []
    data = _request("GET", "/location/suggest/cities", params={"name": query, "country_code": "RU"})
    return [
        City(
            code=int(c["code"]),
            name=c.get("full_name", "").split(",")[0],
            full_name=c.get("full_name", ""),
        )
        for c in (data if isinstance(data, list) else [])[:limit]
        if isinstance(c, dict) and c.get("code")
    ]


def city_name(city_code: int) -> str:
    """Название города по коду СДЭК («» — такого кода нет)."""
    data = _request("GET", "/location/cities", params={"code": int(city_code)})
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return str(data[0].get("city") or "")
    return ""


def delivery_points(city_code: int, *, point_type: str = "PVZ") -> list[DeliveryPoint]:
    data = _request("GET", "/deliverypoints", params={"city_code": city_code, "type": point_type})
    points = []
    for p in data if isinstance(data, list) else []:
        if not isinstance(p, dict):
            continue
        location = p.get("location") or {}
        try:
            weight_max = int(p["weight_max"]) if p.get("weight_max") else None
        except (TypeError, ValueError):
            weight_max = None
        points.append(
            DeliveryPoint(
                code=str(p.get("code", "")),
                name=str(p.get("name", "")),
                address=str(location.get("address_full") or location.get("address") or ""),
                work_time=str(p.get("work_time", "")),
                latitude=location.get("latitude"),
                longitude=location.get("longitude"),
                weight_max_kg=weight_max,
            )
        )
    return [p for p in points if p.code]


# ── расчёт ────────────────────────────────────────────────────────────────


def _locations(from_code: int, to_code: int) -> dict:
    return {"from_location": {"code": from_code}, "to_location": {"code": to_code}}


def tariff(
    code: int,
    *,
    from_code: int,
    to_code: int,
    parcels: list[Parcel],
    declared_value: Decimal = Decimal("0"),
) -> Tariff:
    """Цена одного тарифа. ``cost`` — ``total_sum``: доставка с услугами и НДС СДЭК.

    ``declared_value`` — объявленная стоимость (страховка); 0 — без страховки.
    """
    payload = {
        "tariff_code": code,
        **_locations(from_code, to_code),
        "packages": [_package(p) for p in parcels],
    }
    if declared_value > 0:
        payload["services"] = [{"code": "INSURANCE", "parameter": str(declared_value)}]
    data = _request("POST", "/calculator/tariff", json=payload)
    if not isinstance(data, dict) or data.get("errors"):
        raise CdekError("СДЭК не посчитал тариф", retryable=False)
    total = data.get("total_sum", data.get("delivery_sum"))
    if total is None:
        raise _unavailable("нет суммы в ответе тарифа")
    return Tariff(
        code=code,
        name="",
        delivery_mode=int(data.get("delivery_mode") or 0),
        cost=Decimal(str(total)).quantize(Decimal("0.01")),
        period_min=int(data.get("period_min") or 0),
        period_max=int(data.get("period_max") or 0),
    )


def tariff_list(*, from_code: int, to_code: int, parcels: list[Parcel]) -> list[Tariff]:
    """Все тарифы маршрута. ``cost`` здесь — ``delivery_sum`` без услуг и НДС: годится
    только для выбора тарифа, цену покупателю даёт ``tariff()``."""
    data = _request(
        "POST",
        "/calculator/tarifflist",
        json={**_locations(from_code, to_code), "packages": [_package(p) for p in parcels]},
    )
    tariffs = []
    for t in (data.get("tariff_codes") if isinstance(data, dict) else None) or []:
        try:
            tariffs.append(
                Tariff(
                    code=int(t["tariff_code"]),
                    name=str(t.get("tariff_name", "")),
                    delivery_mode=int(t.get("delivery_mode") or 0),
                    cost=Decimal(str(t["delivery_sum"])).quantize(Decimal("0.01")),
                    period_min=int(t.get("period_min") or 0),
                    period_max=int(t.get("period_max") or 0),
                )
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue  # строка без кода или суммы в выбор не идёт
    return tariffs


# ── заказы ────────────────────────────────────────────────────────────────


def create_order(payload: dict) -> str:
    """Зарегистрировать заказ. Возвращает uuid; проверка приёма — ``get_order``."""
    data = _request("POST", "/orders", json=payload)
    uuid = (data.get("entity") or {}).get("uuid")
    if not uuid:
        raise CdekError("СДЭК не вернул uuid заказа", retryable=False)
    return uuid


def get_order(uuid: str) -> dict:
    return _request("GET", f"/orders/{uuid}")
