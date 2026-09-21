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


# PF-SH-RELEASE-01: SSR витрины ходит в Django напрямую (http://web:8000) без
# X-Forwarded-For, поэтому для DRF все посетители сайта — один IP контейнера фронта.
# Общий анонимный лимит превращался в 429 → SSR 500 на карточках при обходе краулером.
# Доверенный SSR подтверждает себя секретом из окружения и под анонимный лимит не попадает;
# прямые запросы к /api/ снаружи лимитируются как раньше (nginx вырезает заголовок).


@pytest.mark.django_db
def test_ssr_token_bypasses_anon_limit(leaf):
    cache.clear()
    with override_settings(REST_FRAMEWORK=_rf_with(anon="1/min"), SSR_INTERNAL_TOKEN="s3cret"):
        client = APIClient(HTTP_X_SSR_TOKEN="s3cret")
        url = f"/api/catalog/categories/{leaf.slug}/facets/"
        assert [client.get(url).status_code != 429 for _ in range(3)] == [True, True, True]


@pytest.mark.django_db
def test_wrong_ssr_token_is_throttled(leaf):
    cache.clear()
    with override_settings(REST_FRAMEWORK=_rf_with(anon="1/min"), SSR_INTERNAL_TOKEN="s3cret"):
        client = APIClient(HTTP_X_SSR_TOKEN="guess")
        url = f"/api/catalog/categories/{leaf.slug}/facets/"
        assert client.get(url).status_code != 429
        assert client.get(url).status_code == 429


@pytest.mark.django_db
def test_ssr_header_ignored_when_token_not_configured(leaf):
    """Пустой SSR_INTERNAL_TOKEN (дефолт) — обхода нет, даже с пустым заголовком."""
    cache.clear()
    with override_settings(REST_FRAMEWORK=_rf_with(anon="1/min"), SSR_INTERNAL_TOKEN=""):
        client = APIClient(HTTP_X_SSR_TOKEN="")
        url = f"/api/catalog/categories/{leaf.slug}/facets/"
        assert client.get(url).status_code != 429
        assert client.get(url).status_code == 429
