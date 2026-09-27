"""СДЭК (DRF-2299): клиент API и выбор тарифа. Сеть не трогаем — requests подменён.

Живой прогон против тестового контура — ``test_cdek_live.py`` (маркер ``cdek_live``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import requests
from django.core.cache import cache

from apps.integration_ship import services as ship
from apps.integration_ship.ports import Parcel
from apps.integration_ship.providers import cdek

PARCEL = Parcel(weight_g=2000, length_cm=30, width_cm=20, height_cm=10)


class _Resp:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture(autouse=True)
def _cdek_settings(settings):
    cache.clear()
    settings.FEATURES = {**settings.FEATURES, "external_ship": True}
    settings.SHIP_PROVIDER = "cdek"
    settings.CDEK_API_URL = ""
    settings.CDEK_ACCOUNT = ""
    settings.CDEK_SECURE = ""
    settings.CDEK_SHIP_FROM = "warehouse"
    settings.CDEK_TARIFF_PVZ = 0
    settings.CDEK_TARIFF_COURIER = 0
    yield
    cache.clear()


@pytest.fixture
def http(monkeypatch):
    """Подмена requests: token — через post, остальное — через request."""
    calls = {"token": 0, "request": []}
    replies: list = []

    def fake_post(url, params=None, timeout=None):
        calls["token"] += 1
        return _Resp(200, {"access_token": f"tok{calls['token']}", "expires_in": 3600})

    def fake_request(method, url, params=None, json=None, headers=None, timeout=None):
        calls["request"].append({"method": method, "url": url, "json": json, "headers": headers})
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(cdek.requests, "post", fake_post)
    monkeypatch.setattr(cdek.requests, "request", fake_request)
    return calls, replies


# ── клиент ────────────────────────────────────────────────────────────────


def test_тестовые_ключи_только_для_тестового_контура(settings):
    assert cdek.is_configured()
    settings.CDEK_API_URL = "https://api.cdek.ru/v2"
    assert not cdek.is_configured()
    settings.CDEK_ACCOUNT, settings.CDEK_SECURE = "acc", "sec"
    assert cdek.is_configured()


def test_токен_берётся_один_раз_и_живёт_в_кеше(http):
    calls, replies = http
    replies.extend([_Resp(200, []), _Resp(200, [])])
    cdek.delivery_points(504)
    cdek.delivery_points(504)
    assert calls["token"] == 1
    assert calls["request"][0]["headers"]["Authorization"] == "Bearer tok1"


def test_401_один_раз_обновляет_токен(http):
    calls, replies = http
    replies.extend([_Resp(401, {}), _Resp(200, [])])
    assert cdek.delivery_points(504) == []
    assert calls["token"] == 2
    assert calls["request"][1]["headers"]["Authorization"] == "Bearer tok2"


def test_5xx_и_сеть_повторяемые_4xx_нет(http):
    _, replies = http
    replies.append(_Resp(502, ValueError("not json")))
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert err.value.retryable and err.value.status == 502

    cache.delete(cdek._DOWN_KEY)
    replies.append(requests.ConnectTimeout("boom"))
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert err.value.retryable
    cache.delete(cdek._DOWN_KEY)

    replies.append(_Resp(400, {"errors": [{"code": "v2_recipient_location_not_recognized"}]}))
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert not err.value.retryable
    assert "v2_recipient_location_not_recognized" in str(err.value)


def test_тариф_цена_с_ндс_и_страховка_на_стоимость_товаров(http):
    calls, replies = http
    replies.append(
        _Resp(200, {"delivery_sum": 340.0, "total_sum": 948.0, "period_min": 2, "period_max": 4})
    )
    t = cdek.tariff(
        136, from_code=504, to_code=44, parcels=[PARCEL], declared_value=Decimal("50000")
    )
    assert t.cost == Decimal("948.00")
    assert (t.period_min, t.period_max) == (2, 4)
    body = calls["request"][0]["json"]
    assert body["services"] == [{"code": "INSURANCE", "parameter": "50000"}]
    assert body["packages"] == [{"weight": 2000, "length": 30, "width": 20, "height": 10}]
    assert body["from_location"] == {"code": 504} and body["to_location"] == {"code": 44}


def test_ошибка_в_теле_200_не_становится_ценой(http):
    _, replies = http
    replies.append(_Resp(200, {"errors": [{"code": "ve_calc_weight"}]}))
    with pytest.raises(cdek.CdekError) as err:
        cdek.tariff(136, from_code=504, to_code=44, parcels=[PARCEL])
    assert not err.value.retryable


def test_после_сбоя_минуту_не_ходим_в_сдэк(http):
    calls, replies = http
    replies.append(requests.ReadTimeout("slow"))
    with pytest.raises(cdek.CdekError):
        cdek.delivery_points(504)
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)  # запрос не уходит: replies пуст, иначе IndexError
    assert err.value.retryable
    assert len(calls["request"]) == 1


def test_непонятный_ответ_это_недоступность_а_не_500(http, monkeypatch):
    _, replies = http
    replies.append(_Resp(200, ValueError("<html>")))
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert err.value.retryable

    cache.clear()
    monkeypatch.setattr(cdek.requests, "post", lambda *a, **k: _Resp(200, {"token": "x"}))
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert err.value.retryable


def test_кеш_недоступен_клиент_работает(http, monkeypatch):
    calls, replies = http

    def broken(*a, **k):
        raise ConnectionError("redis down")

    for name in ("get", "set", "delete"):
        monkeypatch.setattr(cdek.cache, name, broken)
    replies.append(_Resp(200, []))
    assert cdek.delivery_points(504) == []


def test_отвергнутые_ключи_помечены(http, monkeypatch):
    _, replies = http
    replies.extend([_Resp(401, {}), _Resp(401, {})])
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert err.value.auth and not err.value.retryable

    cache.clear()
    monkeypatch.setattr(cdek.requests, "post", lambda *a, **k: _Resp(401, {}))
    with pytest.raises(cdek.CdekError) as err:
        cdek.delivery_points(504)
    assert err.value.auth


def test_пункт_выдачи_без_сырого_json_но_с_лимитом_веса(http):
    _, replies = http
    replies.append(
        _Resp(
            200,
            [
                {
                    "code": "PNZ1",
                    "name": "Пенза",
                    "weight_max": 15,
                    "location": {"address": "Мира, 1"},
                    "big": "x" * 1000,
                }
            ],
        )
    )
    (point,) = cdek.delivery_points(504)
    assert point.weight_max_kg == 15 and point.address == "Мира, 1"
    assert not hasattr(point, "raw")


# ── выбор тарифа ──────────────────────────────────────────────────────────


def _tariff(code, cost, mode=4):
    return cdek.Tariff(code=code, name="", delivery_mode=mode, cost=Decimal(cost), period_min=1)


def _quote(mode="pvz"):
    return ship.cdek_quote(
        to_city_code=44, mode=mode, parcels=[PARCEL], declared_value=Decimal("1000")
    )


def test_выключенный_флаг_или_stub_это_ручной_расчёт_а_не_ноль(settings, monkeypatch):
    monkeypatch.setattr(cdek, "tariff", lambda *a, **k: pytest.fail("СДЭК не должен вызываться"))
    settings.FEATURES = {**settings.FEATURES, "external_ship": False}
    assert _quote() == ship.CarrierQuote(cost=None, reason=ship.PROVIDER_DISABLED)
    settings.FEATURES = {**settings.FEATURES, "external_ship": True}
    settings.SHIP_PROVIDER = "stub"
    assert _quote().reason == ship.PROVIDER_DISABLED


def test_настроенный_тариф_режима(settings, monkeypatch):
    seen = []

    def fake_tariff(code, **kw):
        seen.append(code)
        return _tariff(code, "408.00")

    monkeypatch.setattr(cdek, "tariff", fake_tariff)
    assert _quote("pvz").cost == Decimal("408.00")
    assert _quote("courier").tariff_code == 137
    settings.CDEK_SHIP_FROM = "door"
    _quote("pvz")
    settings.CDEK_TARIFF_COURIER = 482
    _quote("courier")
    assert seen == [136, 137, 138, 482]


def test_нет_настроенного_тарифа_берём_самый_дешёвый_того_же_режима(monkeypatch):
    def fake_tariff(code, **kw):
        if code == 136:
            raise cdek.CdekError("нет тарифа", retryable=False, status=400)
        return _tariff(code, {234: "300.00", 368: "250.00"}[code])

    monkeypatch.setattr(cdek, "tariff", fake_tariff)
    monkeypatch.setattr(
        cdek,
        "tariff_list",
        lambda **kw: [
            _tariff(368, "200.00", mode=4),
            _tariff(234, "150.00", mode=4),
            _tariff(137, "100.00", mode=3),  # курьер — другой режим, не берём
        ],
    )
    q = _quote("pvz")
    assert (q.tariff_code, q.cost) == (234, Decimal("300.00"))


def test_отказавший_настроенный_тариф_не_запрашиваем_повторно(monkeypatch):
    seen = []

    def fake_tariff(code, **kw):
        seen.append(code)
        raise cdek.CdekError("нет тарифа", retryable=False, status=400)

    monkeypatch.setattr(cdek, "tariff", fake_tariff)
    monkeypatch.setattr(
        cdek, "tariff_list", lambda **kw: [_tariff(136, "100.00"), _tariff(234, "150.00")]
    )
    assert _quote("pvz").reason == ship.NO_TARIFF
    assert seen == [136, 234]


def test_неверные_ключи_это_недоступность_и_ошибка_в_логе(monkeypatch, caplog):
    def fake_tariff(code, **kw):
        raise cdek.CdekError("СДЭК HTTP 401", retryable=False, status=401, auth=True)

    monkeypatch.setattr(cdek, "tariff", fake_tariff)
    monkeypatch.setattr(cdek, "tariff_list", lambda **kw: pytest.fail("не подбираем тариф"))
    with caplog.at_level("ERROR"):
        assert _quote().reason == ship.PROVIDER_UNAVAILABLE
    assert "ключи" in caplog.text


def test_пустой_ответ_справочника_не_кешируется(monkeypatch):
    calls = []
    monkeypatch.setattr(cdek, "delivery_points", lambda code, **kw: calls.append(code) or [])
    ship.cdek_points(504)
    ship.cdek_points(504)
    assert calls == [504, 504]


def test_тарифа_нет_или_сдэк_недоступен_это_разные_причины(monkeypatch):
    monkeypatch.setattr(
        cdek,
        "tariff",
        lambda code, **kw: (_ for _ in ()).throw(cdek.CdekError("x", retryable=False)),
    )
    monkeypatch.setattr(cdek, "tariff_list", lambda **kw: [])
    assert _quote().reason == ship.NO_TARIFF

    cache.clear()
    monkeypatch.setattr(
        cdek,
        "tariff",
        lambda code, **kw: (_ for _ in ()).throw(cdek.CdekError("x", retryable=True)),
    )
    assert _quote().reason == ship.PROVIDER_UNAVAILABLE


def test_цена_маршрута_кешируется(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cdek, "tariff", lambda code, **kw: calls.append(code) or _tariff(code, "408.00")
    )
    _quote()
    _quote()
    assert calls == [136]
