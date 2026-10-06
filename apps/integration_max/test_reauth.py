"""DRF-2497: подтверждение личности через привязанный MAX (операция CONFIRM_LOGIN).

Засчитывается только MAX, привязанный к тому же пользователю; никого не создаёт,
не привязывает и не впускает. Отметку в сессию ставит ввод кода из бота (DRF-2740).
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import reauth

from . import services
from .models import MaxAccount, MaxAuthAttempt
from .tests import TOKEN, _make_vcf_payload, code_from_reply

User = get_user_model()
Status = MaxAuthAttempt.Status
Operation = MaxAuthAttempt.Operation
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
HDR = {"HTTP_X_MAX_BOT_API_SECRET": "wh-secret"}


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.MAX_BOT_TOKEN = TOKEN
    settings.MAX_BOT_USERNAME = "test_auth_bot"
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def owner(db):
    user = User.objects.create_user(phone="+79001230001", password=None)
    MaxAccount.objects.create(user=user, max_user_id=7001, phone=user.phone)
    return user


@pytest.fixture
def api(owner):
    """Сессия владельца, открытая давно: отметки о свежем входе нет."""
    client = APIClient()
    client.force_login(owner, backend=MODEL_BACKEND)
    session = client.session
    session.pop(reauth.SESSION_KEY, None)
    session.save()
    return client


def _bot_started(api, token: str, max_user_id: int | None, chat_id: int = 900):
    payload = {"update_type": "bot_started", "timestamp": 1, "chat_id": chat_id, "payload": token}
    payload["user"] = {"user_id": max_user_id} if max_user_id else {}
    return APIClient().post(
        "/api/max/webhook/", data=json.dumps(payload), content_type="application/json", **HDR
    )


def _start(api) -> dict:
    resp = api.post("/api/account/max/reauth/")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ═══════════ Старт ═══════════


@pytest.mark.django_db
def test_старт_создаёт_попытку_подтверждения(api, owner):
    data = _start(api)
    attempt = MaxAuthAttempt.objects.get(public_id=data["attempt_id"])
    assert attempt.operation_type == Operation.CONFIRM_LOGIN and attempt.user_id == owner.pk


@pytest.mark.django_db
def test_старт_без_привязанного_max(db):
    user = User.objects.create_user(phone="+79001230002", password=None)
    client = APIClient()
    client.force_login(user, backend=MODEL_BACKEND)
    assert client.post("/api/account/max/reauth/").status_code == 400


@pytest.mark.django_db
def test_старт_у_пользователя_с_паролем(db):
    user = User.objects.create_user(phone="+79001230003", password="pass12345")
    MaxAccount.objects.create(user=user, max_user_id=7003, phone=user.phone)
    client = APIClient()
    client.force_login(user, backend=MODEL_BACKEND)
    assert client.post("/api/account/max/reauth/").status_code == 400


# ═══════════ Бот ═══════════


@override_settings(MAX_WEBHOOK_SECRET="wh-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.django_db
def test_тот_же_max_получает_код_и_ввод_кода_ставит_отметку(mock_send, api, owner):
    data = _start(api)
    token = data["deeplink"].split("start=", 1)[1]
    _bot_started(api, token, 7001)
    reply = mock_send.call_args[0][0]
    assert "удаление аккаунта" in reply["text"]  # что именно подтверждается
    code = code_from_reply(reply)

    # Опрос статуса отметку не ставит: попытка ждёт код.
    resp = api.get(f"/api/auth/max/{data['attempt_id']}/status/")
    assert resp.json()["status"] == "confirmation_required"
    assert api.get("/api/account/me/").json()["reauth_valid_until"] is None

    resp = api.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    me = api.get("/api/account/me/").json()
    assert me["id"] == owner.pk and me["reauth_valid_until"] is not None
    # Повторный ввод/опрос окно не продлевает: время — момент подтверждения.
    first = api.session[reauth.SESSION_KEY]["at"]
    api.get(f"/api/auth/max/{data['attempt_id']}/status/")
    assert api.session[reauth.SESSION_KEY]["at"] == first
    assert api.post("/api/account/delete/").status_code == 200


@override_settings(MAX_WEBHOOK_SECRET="wh-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.django_db
def test_код_подтверждения_из_чужой_сессии_не_принимается(mock_send, api, owner):
    """Угнанная ссылка: даже с верным кодом чужой браузер отметку не получит."""
    data = _start(api)
    _bot_started(api, data["deeplink"].split("start=", 1)[1], 7001)
    code = code_from_reply(mock_send.call_args[0][0])
    stranger = APIClient()
    assert (
        stranger.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code}).status_code
        == 404
    )
    other_user = User.objects.create_user(phone="+79001230008", password=None)
    stranger.force_login(other_user, backend=MODEL_BACKEND)
    assert (
        stranger.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code}).status_code
        == 404
    )


@override_settings(MAX_WEBHOOK_SECRET="wh-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.django_db
def test_чужой_max_не_подтверждает(mock_send, api, owner):
    stranger = User.objects.create_user(phone="+79001230009", password=None)
    MaxAccount.objects.create(user=stranger, max_user_id=7009, phone=stranger.phone)
    data = _start(api)
    _bot_started(api, data["deeplink"].split("start=", 1)[1], 7009)

    attempt = MaxAuthAttempt.objects.get(public_id=data["attempt_id"])
    assert attempt.status == Status.FAILED and attempt.failure_reason == "reauth_mismatch"
    assert "не привязан" in mock_send.call_args[0][0]["text"]
    api.get(f"/api/auth/max/{data['attempt_id']}/status/")
    assert api.get("/api/account/me/").json()["reauth_valid_until"] is None
    assert api.post("/api/account/delete/").status_code == 403


@override_settings(MAX_WEBHOOK_SECRET="wh-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.django_db
def test_старт_без_id_пользователя_max_отказ(mock_send, api):
    data = _start(api)
    _bot_started(api, data["deeplink"].split("start=", 1)[1], None)
    attempt = MaxAuthAttempt.objects.get(public_id=data["attempt_id"])
    assert attempt.status == Status.FAILED and attempt.failure_reason == "reauth_mismatch"


@override_settings(MAX_WEBHOOK_SECRET="wh-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.django_db
def test_контакт_после_подтверждения_никого_не_создаёт(mock_send, api):
    """Номер, присланный следом за стартом по диплинку, до попытки не доходит."""
    data = _start(api)
    _bot_started(api, data["deeplink"].split("start=", 1)[1], 7555, chat_id=901)
    users_before = User.objects.count()
    vcf = _make_vcf_payload("+79009998877", TOKEN)
    APIClient().post(
        "/api/max/webhook/",
        data=json.dumps(
            {
                "update_type": "message_created",
                "timestamp": 2,
                "message": {
                    "sender": {"user_id": 7555},
                    "recipient": {"chat_id": 901, "chat_type": "dialog"},
                    "body": {"mid": "c1", "attachments": [{"type": "contact", "payload": vcf}]},
                },
            }
        ),
        content_type="application/json",
        **HDR,
    )
    assert User.objects.count() == users_before
    assert not MaxAccount.objects.filter(max_user_id=7555).exists()


@pytest.mark.django_db
def test_решение_по_подтверждению_с_чужим_max_отказ(owner):
    attempt = services.create_attempt(
        session_key="s", operation_type=Operation.CONFIRM_LOGIN, user=owner
    ).attempt
    decision = services.decide(attempt, max_user_id=7777, phone="+79005554433")
    assert not decision.ok and decision.reason == "reauth_mismatch"
    assert not User.objects.filter(phone="+79005554433").exists()


# ═══════════ Опрос статуса: что НЕ ставит отметку ═══════════


def _completed_attempt(api, owner, op, *, ago=timedelta(0)):
    attempt = services.create_attempt(
        session_key=api.session.session_key, operation_type=op, user=owner
    ).attempt
    MaxAuthAttempt.objects.filter(pk=attempt.pk).update(
        status=Status.COMPLETED, completed_at=timezone.now() - ago
    )
    return attempt


@pytest.mark.django_db
@pytest.mark.parametrize("op", [Operation.LINK, Operation.LOGIN])
def test_другие_операции_не_подтверждают(api, owner, op):
    attempt = _completed_attempt(api, owner, op)
    api.get(f"/api/auth/max/{attempt.public_id}/status/")
    assert api.get("/api/account/me/").json()["reauth_valid_until"] is None


@pytest.mark.django_db
def test_старое_подтверждение_не_продлевает_окно(api, owner):
    attempt = _completed_attempt(api, owner, Operation.CONFIRM_LOGIN, ago=timedelta(minutes=11))
    api.get(f"/api/auth/max/{attempt.public_id}/status/")
    assert api.get("/api/account/me/").json()["reauth_valid_until"] is None


@pytest.mark.django_db
def test_аноним_не_входит_по_попытке_подтверждения(owner):
    client = APIClient()
    client.get("/api/account/csrf/")
    session = client.session
    session.save()
    attempt = services.create_attempt(
        session_key=session.session_key, operation_type=Operation.CONFIRM_LOGIN, user=owner
    ).attempt
    MaxAuthAttempt.objects.filter(pk=attempt.pk).update(
        status=Status.COMPLETED, completed_at=timezone.now()
    )
    client.get(f"/api/auth/max/{attempt.public_id}/status/")
    assert client.get("/api/account/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_старая_попытка_не_затирает_свежую_отметку(api, owner):
    session = api.session
    fresh = int(timezone.now().timestamp())
    session[reauth.SESSION_KEY] = {"at": fresh, "method": reauth.PASSWORD}
    session.save()
    attempt = _completed_attempt(api, owner, Operation.CONFIRM_LOGIN, ago=timedelta(minutes=5))
    api.get(f"/api/auth/max/{attempt.public_id}/status/")
    assert api.session[reauth.SESSION_KEY] == {"at": fresh, "method": reauth.PASSWORD}
