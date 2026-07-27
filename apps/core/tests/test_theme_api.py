"""Тесты API темы оформления (#76)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import SiteSettings


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def settings_obj(db):
    s = SiteSettings.get_solo()
    s.name = "Тест-магазин"
    s.primary_color = "#112233"
    s.accent_color = "#aabbcc"
    s.region = "Пензенская область"
    s.contacts = {"phone": "+7 8412 00-00-00", "address": "г. Пенза"}
    s.save()
    return s


@pytest.mark.django_db
def test_theme_returns_colors(client, settings_obj):
    url = reverse("core:theme")
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["primary_color"] == "#112233"
    assert data["accent_color"] == "#aabbcc"
    assert data["name"] == "Тест-магазин"
    assert data["region"] == "Пензенская область"
    assert data["contacts"]["phone"] == "+7 8412 00-00-00"


@pytest.mark.django_db
def test_theme_logo_url_empty_by_default(client, db):
    url = reverse("core:theme")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json()["logo_url"] == ""


@pytest.mark.django_db
def test_theme_unauthenticated(client, db):
    url = reverse("core:theme")
    resp = client.get(url)
    assert resp.status_code == 200
