"""Глобальный AnonRateThrottle на каталоге/фасетах (#279).

Тест проверяет, что анонимный DoS на дорогих эндпоинтах (фасеты) ограничивается
429 после превышения лимита. Аутентифицированный запрос тот же лимит не получает.
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


@pytest.fixture()
def leaf(db):
    from apps.catalog.models import Category

    root = Category.add_root(name="Root", slug="root", on_site=True, is_active=True)
    child = root.add_child(name="Дрели", slug="dreli", on_site=True, is_active=True)
    return child


@pytest.mark.django_db
def test_anon_facets_throttled(leaf):
    """Анонимный клиент получает 429 после превышения лимита на фасетах."""
    cache.clear()
    with override_settings(REST_FRAMEWORK=_rf_with(anon="2/min")):
        client = APIClient()
        url = f"/api/catalog/categories/{leaf.slug}/facets/"
        assert client.get(url).status_code != 429
        assert client.get(url).status_code != 429
        assert client.get(url).status_code == 429


@pytest.mark.django_db
def test_authenticated_user_not_throttled_by_anon_limit(leaf, django_user_model):
    """Аутентифицированный пользователь не ограничивается AnonRateThrottle."""
    cache.clear()
    with override_settings(REST_FRAMEWORK=_rf_with(anon="1/min")):
        user = django_user_model.objects.create_user(phone="+79990000099", password="pass")
        client = APIClient()
        client.force_authenticate(user=user)
        url = f"/api/catalog/categories/{leaf.slug}/facets/"
        # 3 запроса подряд — аутентифицированный не должен получить 429
        assert client.get(url).status_code != 429
        assert client.get(url).status_code != 429
        assert client.get(url).status_code != 429
