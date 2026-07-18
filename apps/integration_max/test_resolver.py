"""Тесты canonical resolver MAX-получателя (#514)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import MaxAccount
from .services import resolve_active_chat_id, unlink_max

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass123")


def _make_account(user, *, max_user_id=777, chat_id=555, is_active=True) -> MaxAccount:
    return MaxAccount.objects.create(
        user=user,
        max_user_id=max_user_id,
        chat_id=chat_id,
        phone=user.phone,
        is_active=is_active,
        phone_verified_at=timezone.now(),
    )


@pytest.mark.django_db
def test_resolver_none_user():
    assert resolve_active_chat_id(None) is None


@pytest.mark.django_db
def test_resolver_no_recipient_at_all(user):
    assert resolve_active_chat_id(user) is None


@pytest.mark.django_db
def test_resolver_canonical_max_account(user):
    """Регрессия #514: MaxAccount.chat_id есть, User.max_chat_id пуст → resolved."""
    _make_account(user, chat_id=555)
    assert resolve_active_chat_id(user) == 555


@pytest.mark.django_db
def test_resolver_legacy_only_fallback(user):
    """Legacy-only: нет MaxAccount, есть только старое User.max_chat_id."""
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    user.refresh_from_db()
    assert resolve_active_chat_id(user) == 999


@pytest.mark.django_db
def test_resolver_conflict_canonical_wins(user):
    """Конфликт: оба поля заданы и расходятся — канонический MaxAccount побеждает."""
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    user.refresh_from_db()
    _make_account(user, chat_id=555)
    assert resolve_active_chat_id(user) == 555


@pytest.mark.django_db
def test_resolver_inactive_account_ignored(user):
    """Неактивная привязка не считается получателем — резолвер падает на legacy."""
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    user.refresh_from_db()
    _make_account(user, chat_id=555, is_active=False)
    assert resolve_active_chat_id(user) == 999


@pytest.mark.django_db
def test_resolver_account_without_chat_id_ignored(user):
    """MaxAccount без chat_id (ещё не запомнили диалог) — не годный получатель."""
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    user.refresh_from_db()
    _make_account(user, chat_id=None)
    assert resolve_active_chat_id(user) == 999


@pytest.mark.django_db
def test_resolver_unlink_stops_resolution(user):
    """Unlink немедленно прекращает резолв через MaxAccount (AC #514)."""
    _make_account(user, chat_id=555)
    assert resolve_active_chat_id(user) == 555
    assert unlink_max(user) is True
    assert resolve_active_chat_id(user) is None


@pytest.mark.django_db
def test_resolver_unlink_falls_back_to_legacy(user):
    """Unlink канонической привязки не трогает legacy-поле — оно остаётся fallback."""
    User.objects.filter(pk=user.pk).update(max_chat_id=999)
    user.refresh_from_db()
    _make_account(user, chat_id=555)
    assert unlink_max(user) is True
    assert resolve_active_chat_id(user) == 999
