"""Тесты авторизации через MAX по модели одноразовой попытки (#492, сценарии §17).

Покрывают: регистрацию нового пользователя, привязку существующего, повторный вход,
привязку из ЛК и конфликты, TTL/повторное использование, привязку к браузер-сессии,
webhook e2e (диплинк-старт → контакт → вход на сайте).
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import services
from .models import MaxAccount, MaxAuthAttempt
from .tests import TOKEN, _make_vcf_payload

User = get_user_model()
Status = MaxAuthAttempt.Status
Operation = MaxAuthAttempt.Operation
PHONE = "+79001234567"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


def _mk_user(phone=PHONE, **kw):
    return User.objects.create_user(phone=phone, password="pass12345", **kw)


def _attempt(op=Operation.LOGIN, user=None, session="sess-1"):
    return services.create_attempt(session_key=session, operation_type=op, user=user).attempt


# ═══════════ Сервис: поиск/создание пользователя (§10) ═══════════


@pytest.mark.django_db
def test_register_new_user_via_contact():
    """Пользователь не найден → создаётся аккаунт (passwordless, телефон подтверждён)."""
    attempt = _attempt()
    res = services.complete_from_contact(attempt, max_user_id=1001, phone=PHONE, chat_id=500)
    assert res.status == Status.COMPLETED
    user = res.user
    assert user.phone == PHONE
    assert user.phone_verified is True
    assert user.has_usable_password() is False
    acct = MaxAccount.objects.get(max_user_id=1001)
    assert acct.user_id == user.pk and acct.chat_id == 500


@pytest.mark.django_db
def test_existing_user_linked_and_logged_in():
    """Найден по телефону, MAX не привязан → привязать + вход."""
    user = _mk_user(phone_verified=False)
    attempt = _attempt()
    res = services.complete_from_contact(attempt, max_user_id=1002, phone=PHONE)
    assert res.status == Status.COMPLETED and res.user_id == user.pk
    user.refresh_from_db()
    assert user.phone_verified is True
    assert MaxAccount.objects.filter(user=user, max_user_id=1002).exists()


@pytest.mark.django_db
def test_repeat_login_without_number():
    """MAX уже привязан → повторный вход по подтверждению (без передачи номера)."""
    user = _mk_user()
    MaxAccount.objects.create(user=user, max_user_id=1003, phone=PHONE)
    attempt = _attempt()
    res = services.complete_confirm(attempt, max_user_id=1003, chat_id=7)
    assert res.status == Status.COMPLETED and res.user_id == user.pk


@pytest.mark.django_db
def test_link_from_account_success():
    """Привязка из ЛК: телефон совпал, конфликта нет → привязано."""
    user = _mk_user()
    attempt = _attempt(op=Operation.LINK, user=user)
    res = services.complete_from_contact(attempt, max_user_id=1004, phone=PHONE)
    assert res.status == Status.COMPLETED
    assert MaxAccount.objects.filter(user=user, max_user_id=1004).exists()


@pytest.mark.django_db
def test_link_conflict_max_belongs_to_other():
    """MAX уже привязан к другому аккаунту → конфликт, объединения нет."""
    other = _mk_user(phone="+79990000000")
    MaxAccount.objects.create(user=other, max_user_id=1005, phone=other.phone)
    user = _mk_user(phone=PHONE)
    attempt = _attempt(op=Operation.LINK, user=user)
    res = services.complete_from_contact(attempt, max_user_id=1005, phone=PHONE)
    assert res.status == Status.FAILED and res.failure_reason == "max_linked_to_other"
    assert not MaxAccount.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_link_phone_mismatch():
    """Привязка из ЛК: номер MAX не совпал с номером аккаунта → отказ."""
    user = _mk_user(phone=PHONE)
    attempt = _attempt(op=Operation.LINK, user=user)
    res = services.complete_from_contact(attempt, max_user_id=1006, phone="+79995550000")
    assert res.status == Status.FAILED and res.failure_reason == "phone_mismatch"


@pytest.mark.django_db
def test_conflict_user_has_other_max():
    """У найденного по телефону аккаунта уже есть другая привязка MAX → конфликт."""
    user = _mk_user(phone=PHONE)
    MaxAccount.objects.create(user=user, max_user_id=1007, phone=PHONE)
    attempt = _attempt()
    res = services.complete_from_contact(attempt, max_user_id=2007, phone=PHONE)
    assert res.status == Status.FAILED and res.failure_reason == "user_has_other_max"


@pytest.mark.django_db
def test_expired_attempt_cannot_complete():
    """Истёкшая попытка (§11.3) не завершается."""
    attempt = _attempt()
    MaxAuthAttempt.objects.filter(pk=attempt.pk).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    attempt.refresh_from_db()
    res = services.complete_from_contact(attempt, max_user_id=1008, phone=PHONE)
    assert res.status in (Status.EXPIRED, Status.FAILED)
    assert not User.objects.filter(phone=PHONE).exists()


@pytest.mark.django_db
def test_complete_is_idempotent():
    """Повторная доставка того же контакта не создаёт дублей (§11.4)."""
    attempt = _attempt()
    services.complete_from_contact(attempt, max_user_id=1009, phone=PHONE, chat_id=1)
    attempt.refresh_from_db()
    services.complete_from_contact(attempt, max_user_id=1009, phone=PHONE, chat_id=1)
    assert MaxAccount.objects.filter(max_user_id=1009).count() == 1
    assert User.objects.filter(phone=PHONE).count() == 1


# ═══════════ Эндпоинты и e2e ═══════════


@pytest.mark.django_db
def test_start_returns_deeplink_without_pii(api):
    resp = api.post("/api/auth/max/start/")
    assert resp.status_code == 201
    data = resp.json()
    assert data["attempt_id"] and data["status"] == "pending"
    assert data["deeplink"].startswith("https://max.ru/")
    assert "start=" in data["deeplink"]
    assert PHONE not in data["deeplink"]  # §11.1: без PII


@pytest.mark.django_db
def test_status_binds_to_creating_session(api):
    """Статус/вход доступны только браузеру, создавшему попытку (§11.2)."""
    start = api.post("/api/auth/max/start/").json()
    attempt = MaxAuthAttempt.objects.get(public_id=start["attempt_id"])
    services.complete_from_contact(attempt, max_user_id=3001, phone=PHONE)

    # Чужая сессия — 404 (не читает и не логинит).
    other = APIClient()
    assert other.get(f"/api/auth/max/{start['attempt_id']}/status/").status_code == 404

    # Своя сессия — completed + поднятая Django-сессия (последующий /me/ авторизован).
    resp = api.get(f"/api/auth/max/{start['attempt_id']}/status/")
    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    me = api.get("/api/account/me/")
    assert me.status_code == 200 and me.json()["phone"] == PHONE


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="wh-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.django_db
def test_e2e_registration_via_webhook(mock_send, api):
    """Полный поток: старт на сайте → диплинк-старт в боте → контакт → вход на сайте."""
    start = api.post("/api/auth/max/start/").json()
    token = None
    # token содержится в диплинке после start=
    token = start["deeplink"].split("start=", 1)[1]
    hdr = {"HTTP_X_MAX_WEBHOOK_SECRET": "wh-secret"}

    # bot_started по диплинку
    api.post(
        "/api/max/webhook/",
        data=json.dumps(
            {
                "update_type": "bot_started",
                "timestamp": 1,
                "chat_id": 900,
                "user": {"user_id": 4001},
                "payload": token,
            }
        ),
        content_type="application/json",
        **hdr,
    )
    # контакт (штатная передача номера)
    vcf = _make_vcf_payload(PHONE, TOKEN)
    api.post(
        "/api/max/webhook/",
        data=json.dumps(
            {
                "update_type": "message_created",
                "timestamp": 2,
                "message": {
                    "sender": {"user_id": 4001},
                    "recipient": {"chat_id": 900, "chat_type": "dialog"},
                    "body": {"mid": "c1", "attachments": [{"type": "contact", "payload": vcf}]},
                },
            }
        ),
        content_type="application/json",
        **hdr,
    )

    attempt = MaxAuthAttempt.objects.get(public_id=start["attempt_id"])
    assert attempt.status == Status.COMPLETED
    assert User.objects.filter(phone=PHONE).exists()

    # сайт опрашивает статус → входит
    resp = api.get(f"/api/auth/max/{start['attempt_id']}/status/")
    assert resp.json()["status"] == "completed"
    assert api.get("/api/account/me/").status_code == 200


@pytest.mark.django_db
def test_cancel_attempt(api):
    start = api.post("/api/auth/max/start/").json()
    resp = api.post(f"/api/auth/max/{start['attempt_id']}/cancel/")
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    # Контракт единый со status-эндпоинтами: {status, failure_reason} —
    # клиент типизирует ответ как MaxAttemptStatus.
    assert "failure_reason" in resp.json()


@pytest.mark.django_db
def test_link_and_unlink_from_account(api):
    user = _mk_user()
    api.force_login(user)
    # привязка
    start = api.post("/api/account/max/link/").json()
    attempt = MaxAuthAttempt.objects.get(public_id=start["attempt_id"])
    assert attempt.operation_type == Operation.LINK and attempt.user_id == user.pk
    services.complete_from_contact(attempt, max_user_id=5001, phone=PHONE)
    assert api.get("/api/account/max/status/").json()["linked"] is True
    # отвязка
    assert api.post("/api/account/max/unlink/").json()["linked"] is False
    assert not MaxAccount.objects.filter(user=user).exists()


@mock.patch("apps.analytics.services.track")
@pytest.mark.django_db
def test_analytics_events_emitted(mock_track):
    """§15: ключевые события авторизации пишутся в аналитику."""
    attempt = _attempt()
    services.complete_from_contact(attempt, max_user_id=6001, phone=PHONE)
    events = [c.args[0] for c in mock_track.call_args_list]
    assert "max_auth_completed" in events
    assert "max_account_linked" in events
