"""Чей адрес считает лимит запросов.

nginx и BFF передают адрес посетителя последним в X-Forwarded-For; всё, что
клиент дописал в заголовок сам, до этого места не доходит. Без NUM_PROXIES DRF
брал первый адрес цепочки — и лимит входа обходился одним заголовком.
"""

from rest_framework.test import APIRequestFactory

from apps.core.throttling import AuthRateThrottle


def _ident(**meta):
    request = APIRequestFactory().post("/api/account/login/", **meta)
    return AuthRateThrottle().get_ident(request)


def test_берётся_последний_адрес_цепочки():
    assert _ident(HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8", REMOTE_ADDR="10.0.0.9") == "5.6.7.8"


def test_единственный_адрес_от_прокси():
    assert _ident(HTTP_X_FORWARDED_FOR="5.6.7.8", REMOTE_ADDR="10.0.0.9") == "5.6.7.8"


def test_без_заголовка_прямое_соединение():
    assert _ident(REMOTE_ADDR="10.0.0.9") == "10.0.0.9"
