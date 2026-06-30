"""Троттлинг 1С-write-эндпоинтов (#9 код-ревью).

В dev/тестах скоуп onec выключен (см. config/settings/dev.py), поэтому в тесте
включаем лимит через override_settings и проверяем 429 после превышения.
"""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

API_KEY = "throttle-key"


def _rf_with(**rates):
    base = settings.REST_FRAMEWORK
    return {
        **base,
        "DEFAULT_THROTTLE_RATES": {**base["DEFAULT_THROTTLE_RATES"], **rates},
    }


@pytest.mark.django_db
def test_onec_write_endpoint_throttled():
    cache.clear()
    payload = {"items": [{"external_id": "thr-1", "stock": "1"}]}
    with override_settings(REST_FRAMEWORK=_rf_with(onec="2/min"), ONEC_API_KEY=API_KEY):
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=API_KEY)
        assert client.post("/api/1c/stocks/update", payload, format="json").status_code != 429
        assert client.post("/api/1c/stocks/update", payload, format="json").status_code != 429
        assert client.post("/api/1c/stocks/update", payload, format="json").status_code == 429
