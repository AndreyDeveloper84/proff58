"""Троттлинг оформления/корзины гостем (#9 код-ревью).

В dev/тестах скоуп orders выключен (config/settings/dev.py); включаем лимит
через override_settings и проверяем 429 после превышения.
"""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient


def _rf_with(**rates):
    base = settings.REST_FRAMEWORK
    return {
        **base,
        "DEFAULT_THROTTLE_RATES": {**base["DEFAULT_THROTTLE_RATES"], **rates},
    }


@pytest.mark.django_db
def test_cart_add_throttled(product):
    cache.clear()
    with override_settings(REST_FRAMEWORK=_rf_with(orders="2/min")):
        client = APIClient()
        body = {"product_id": product.id, "quantity": 1}
        assert client.post("/api/cart/items/", body, format="json").status_code != 429
        assert client.post("/api/cart/items/", body, format="json").status_code != 429
        assert client.post("/api/cart/items/", body, format="json").status_code == 429
