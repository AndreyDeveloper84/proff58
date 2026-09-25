"""Тесты двухуровневых feature-флагов (#59)."""

import pytest
from django.test import override_settings

from apps.core.features import is_enabled
from apps.core.models import SiteSettings


def test_infra_defaults():
    # eventbus/external_integrations включены по умолчанию, crm/ai — выключены.
    assert is_enabled("eventbus") is True
    assert is_enabled("external_integrations") is True
    assert is_enabled("crm") is False
    assert is_enabled("ai") is False


@override_settings(FEATURES={"crm": True})
def test_infra_env_override():
    assert is_enabled("crm") is True


def test_unknown_flag_is_false():
    assert is_enabled("nonexistent_flag") is False


def test_flag_name_normalized():
    assert is_enabled("  EventBus  ") is True


@pytest.mark.django_db
def test_business_flag_from_db():
    assert is_enabled("reviews") is False  # дефолт SiteSettings
    s = SiteSettings.get_solo()
    s.reviews_enabled = True
    s.save()
    assert is_enabled("reviews") is True


@override_settings(FEATURES={"reviews": True})
@pytest.mark.django_db
def test_business_flag_env_override_beats_db():
    # В БД выключен, но env-override включает — подтверждает двухуровневость.
    s = SiteSettings.get_solo()
    s.reviews_enabled = False
    s.save()
    assert is_enabled("reviews") is True
