"""Тесты management-команды max_recipient_report (#514, read-only отчёт)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from .models import MaxAccount

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass123")


def _run() -> str:
    out = StringIO()
    call_command("max_recipient_report", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_report_empty_when_no_data(user):
    output = _run()
    assert "legacy-only" in output
    assert "0" in output
    assert "конфликт" in output


@pytest.mark.django_db
def test_report_flags_legacy_only_user(user):
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    output = _run()
    assert "legacy-only (есть max_chat_id, нет MaxAccount): 1" in output
    assert f"user={user.pk}" in output


@pytest.mark.django_db
def test_report_flags_conflict(user):
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    MaxAccount.objects.create(
        user=user,
        max_user_id=42,
        chat_id=555,
        phone=user.phone,
        phone_verified_at=timezone.now(),
    )
    output = _run()
    assert "конфликт chat_id (legacy != MaxAccount.chat_id): 1" in output
    assert f"user={user.pk} legacy=999 canonical=555" in output


@pytest.mark.django_db
def test_report_no_conflict_when_chat_ids_match(user):
    User.objects.filter(pk=user.pk).update(max_chat_id=555)
    MaxAccount.objects.create(
        user=user,
        max_user_id=42,
        chat_id=555,
        phone=user.phone,
        phone_verified_at=timezone.now(),
    )
    output = _run()
    assert "конфликт chat_id (legacy != MaxAccount.chat_id): 0" in output
