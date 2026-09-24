"""Реестр условий сброса пароля: модули выше по слоям расширяют правило, не правя accounts."""

import pytest
from django.contrib.auth import get_user_model

from apps.accounts import services

User = get_user_model()


@pytest.fixture
def checks(monkeypatch):
    registry: list = []
    monkeypatch.setattr(services, "_reset_checks", registry)
    return registry


@pytest.mark.django_db
def test_passwordless_needs_registered_check(checks):
    user = User.objects.create_user(phone="+79001119900", email="p@site.ru", password=None)
    assert services.is_reset_eligible(user) is False
    services.register_reset_eligibility(lambda u: u.pk == user.pk)
    assert services.is_reset_eligible(user) is True


@pytest.mark.django_db
def test_registered_check_does_not_open_staff_or_inactive(checks):
    services.register_reset_eligibility(lambda u: True)
    staff = User.objects.create_user(phone="+79001119901", email="s@site.ru", is_staff=True)
    inactive = User.objects.create_user(phone="+79001119902", email="i@site.ru", is_active=False)
    assert services.is_reset_eligible(staff) is False
    assert services.is_reset_eligible(inactive) is False


def test_register_is_idempotent(checks):
    def check(u):
        return True

    services.register_reset_eligibility(check)
    services.register_reset_eligibility(check)
    assert checks == [check]
