"""Контакты магазина в SiteSettings (T3): форма админки пишет в contacts,
seed не затирает заполненное, API темы отдаёт то, что ввели."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.core.admin import SiteSettingsForm
from apps.core.contacts import CONTACT_FIELDS, seed_defaults
from apps.core.models import SiteSettings


def test_seed_заполняет_только_пустое():
    seeded = seed_defaults({"email": "custom@example.com", "phone_display": ""})
    assert seeded["email"] == "custom@example.com"
    assert seeded["phone_display"] == CONTACT_FIELDS["phone_display"][1]
    assert seeded["address"] == CONTACT_FIELDS["address"][1]
    assert seed_defaults(seeded) == seeded  # идемпотентно


@pytest.mark.django_db
def test_миграция_засеяла_контакты():
    s = SiteSettings.get_solo()
    assert s.contacts.get("phone_display") == "8 (8412) 20-20-87"


@pytest.mark.django_db
def test_форма_админки_пишет_в_contacts_и_не_теряет_чужие_ключи():
    s = SiteSettings.get_solo()
    s.contacts = {**s.contacts, "vk": "https://vk.com/x"}
    s.save()
    form = SiteSettingsForm(
        data={
            "name": s.name,
            "primary_color": s.primary_color,
            "accent_color": s.accent_color,
            "region": s.region,
            "requisites": "{}",
            "b2b_enabled": "on",
            "contact_phone_display": "8 (8412) 00-00-00",
            "contact_email": "",
        },
        instance=s,
    )
    assert form.is_valid(), form.errors
    s = form.save()
    assert s.contacts["phone_display"] == "8 (8412) 00-00-00"
    assert s.contacts["email"] == ""  # пустое поле — витрина покажет запасное
    assert s.contacts["vk"] == "https://vk.com/x"


@pytest.mark.django_db
def test_api_темы_отдаёт_контакты():
    s = SiteSettings.get_solo()
    s.contacts = {**s.contacts, "phone_display": "8 (8412) 11-11-11"}
    s.save()
    data = APIClient().get("/api/core/theme/").json()
    assert data["contacts"]["phone_display"] == "8 (8412) 11-11-11"


@pytest.mark.django_db
def test_api_темы_отдаёт_флаг_отзывов_и_он_выключен_миграцией():
    s = SiteSettings.get_solo()
    assert s.reviews_enabled is False
    data = APIClient().get("/api/core/theme/").json()
    assert data["features"] == {"reviews": False}
