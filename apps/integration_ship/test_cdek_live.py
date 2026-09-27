"""Живой прогон клиента СДЭК против тестового контура api.edu.cdek.ru (DRF-2299).

Не входит в обычный прогон и CI: нужен выход в интернет. Запуск:
``CDEK_LIVE=1 pytest -m cdek_live apps/integration_ship/test_cdek_live.py``
(в docker — с ``--network host``).
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from apps.integration_ship.ports import Parcel
from apps.integration_ship.providers import cdek

pytestmark = [
    pytest.mark.cdek_live,
    pytest.mark.skipif(os.environ.get("CDEK_LIVE") != "1", reason="нужен CDEK_LIVE=1"),
]

PENZA, MOSCOW = 504, 44
PARCEL = Parcel(weight_g=2000, length_cm=30, width_cm=20, height_cm=10)


@pytest.fixture(autouse=True)
def _test_contour(settings):
    settings.CDEK_API_URL = cdek.TEST_API_URL
    settings.CDEK_ACCOUNT = ""
    settings.CDEK_SECURE = ""


def test_город_пункты_и_тариф_со_страховкой():
    cities = cdek.suggest_cities("Пенза")
    assert any(c.code == PENZA for c in cities)
    assert cdek.city_name(PENZA) == "Пенза"
    assert cdek.delivery_points(PENZA)

    plain = cdek.tariff(136, from_code=PENZA, to_code=MOSCOW, parcels=[PARCEL])
    insured = cdek.tariff(
        136, from_code=PENZA, to_code=MOSCOW, parcels=[PARCEL], declared_value=Decimal("50000")
    )
    assert plain.cost > 0
    assert insured.cost > plain.cost


def test_тяжелее_предела_тариф_отказывает():
    heavy = Parcel(weight_g=31000, length_cm=60, width_cm=40, height_cm=40)
    with pytest.raises(cdek.CdekError) as err:
        cdek.tariff(136, from_code=PENZA, to_code=MOSCOW, parcels=[heavy])
    assert not err.value.retryable
