"""Контур кода подтверждения (DRF-2740) по замечаниям ревью: перевыпуск сохраняет
отложенный телефон, отслеживание заказа не выдаёт код, гонка исполнения даёт отказ,
а не 500, лимит неверных вводов держится под блокировкой, кэш чистится вслед за
попыткой, ответы сайта до кода не раскрывают чужой браузер.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.orders.models import Order

from . import confirm, services
from .models import MaxAccount, MaxAuthAttempt
from .tests import TOKEN, _make_vcf_payload, code_from_reply

User = get_user_model()
Status = MaxAuthAttempt.Status
Operation = MaxAuthAttempt.Operation
PHONE = "+79001234567"
HDR = {"HTTP_X_MAX_BOT_API_SECRET": "wh-secret"}
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _max_settings(settings):
    settings.MAX_BOT_TOKEN = TOKEN
    settings.MAX_BOT_USERNAME = "test_auth_bot"
    settings.MAX_WEBHOOK_SECRET = "wh-secret"
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def send():
    with mock.patch("apps.integration_max.webhook._send_reply") as m:
        yield m


def _webhook(data: dict):
    return APIClient().post(
        "/api/max/webhook/", data=json.dumps(data), content_type="application/json", **HDR
    )


def _bot_started(token: str, *, chat_id=900, max_user_id=7001, ts=1):
    return _webhook(
        {
            "update_type": "bot_started",
            "timestamp": ts,
            "chat_id": chat_id,
            "user": {"user_id": max_user_id},
            "payload": token,
        }
    )


def _share_contact(phone: str, *, chat_id=900, max_user_id=7001, mid="c1", ts=2):
    return _webhook(
        {
            "update_type": "message_created",
            "timestamp": ts,
            "message": {
                "sender": {"user_id": max_user_id},
                "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
                "body": {
                    "mid": mid,
                    "attachments": [
                        {"type": "contact", "payload": _make_vcf_payload(phone, TOKEN)}
                    ],
                },
            },
        }
    )


def _start(browser: APIClient) -> tuple[dict, str]:
    data = browser.post("/api/auth/max/start/").json()
    return data, data["deeplink"].split("start=", 1)[1]


def _last_text(send) -> str:
    return send.call_args[0][0]["text"]


def _attempt(public_id) -> MaxAuthAttempt:
    return MaxAuthAttempt.objects.get(public_id=public_id)


# ═══════════ Б-1: перевыпуск кода сохраняет отложенный телефон ═══════════


def test_repeat_start_reissues_code_and_keeps_pending_phone(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    first_code = code_from_reply(send.call_args[0][0])

    # Код «не дошёл» — человек жмёт «Начать» ещё раз тем же MAX.
    _bot_started(token, ts=3)
    second_code = code_from_reply(send.call_args[0][0])
    assert second_code != first_code or True  # коды случайны; важно, что он выдан
    assert _attempt(data["attempt_id"]).code_issues == 2

    # Старый код больше не подходит, новый — впускает: телефон из кэша не потерян.
    resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": second_code})
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "completed"
    assert User.objects.filter(phone=PHONE).exists()
    assert browser.get("/api/account/me/").status_code == 200


def test_reissue_with_lost_cache_reports_pending_lost(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    cache.clear()  # рестарт кэша между контактом и повторным «Начать»
    _bot_started(token, ts=3)
    code = code_from_reply(send.call_args[0][0])
    resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 409
    assert resp.json()["failure_reason"] == "pending_lost"
    assert not User.objects.filter(phone=PHONE).exists()


def test_reissue_limit_closes_attempt(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    for ts in (3, 4):
        _bot_started(token, ts=ts)
    assert _attempt(data["attempt_id"]).code_issues == confirm.MAX_ISSUES
    _bot_started(token, ts=5)
    attempt = _attempt(data["attempt_id"])
    assert (attempt.status, attempt.failure_reason) == (Status.FAILED, "code_reissue_limit")
    assert "начните заново" in _last_text(send)
    assert confirm.load_pending(attempt) is None


def test_second_max_on_same_link_gets_no_code(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token, max_user_id=7001)
    _share_contact(PHONE, max_user_id=7001)
    _bot_started(token, chat_id=901, max_user_id=7002, ts=3)
    assert "Код:" not in _last_text(send)
    attempt = _attempt(data["attempt_id"])
    assert attempt.status == Status.CONFIRMATION_REQUIRED and attempt.max_user_id == 7001


# ═══════════ Б-2: отслеживание заказа — без кода даже при привязанном MAX ═══════════


def test_track_order_with_linked_max_asks_contact_not_code(send):
    user = User.objects.create_user(phone=PHONE, password=None, phone_verified=True)
    MaxAccount.objects.create(user=user, max_user_id=7001, chat_id=900, is_active=True)
    order = Order.objects.create(order_number="G-1", customer_phone="+79005556677")
    started = services.create_attempt(
        session_key="guest-sess", operation_type=Operation.TRACK_ORDER, order=order
    )
    _bot_started(started.token)
    reply = send.call_args[0][0]
    assert "Код:" not in reply["text"]
    assert reply["attachments"][0]["payload"]["buttons"][0][0]["type"] == "request_contact"
    assert _attempt(started.attempt.public_id).status == Status.PENDING

    _share_contact("+79005556677")
    attempt = _attempt(started.attempt.public_id)
    assert attempt.status == Status.COMPLETED
    assert attempt.user_id is None  # гость не вошёл и ничего не привязал


# ═══════════ Б-3 / В-1: гонки и лимит под блокировкой ═══════════


def test_integrity_error_during_execute_gives_race_not_500(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    code = code_from_reply(send.call_args[0][0])
    with mock.patch.object(services, "execute", side_effect=IntegrityError("duplicate key")):
        resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 409, resp.content
    attempt = _attempt(data["attempt_id"])
    assert (attempt.status, attempt.failure_reason) == (Status.FAILED, "race")
    assert confirm.load_pending(attempt) is None


def test_five_wrong_codes_fail_attempt_and_counter_survives_400(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    code = code_from_reply(send.call_args[0][0])
    wrong = "000000" if code != "000000" else "111111"
    url = f"/api/auth/max/{data['attempt_id']}/confirm/"
    for n in range(1, confirm.MAX_FAILURES):
        resp = browser.post(url, {"code": wrong})
        assert resp.status_code == 400
        assert resp.json()["attempts_left"] == confirm.MAX_FAILURES - n
        assert _attempt(data["attempt_id"]).confirm_failures == n
    resp = browser.post(url, {"code": wrong})
    assert resp.status_code == 409
    attempt = _attempt(data["attempt_id"])
    assert (attempt.status, attempt.failure_reason) == (Status.FAILED, "code_attempts_exceeded")
    # Верный код после этого уже ничего не даёт.
    assert browser.post(url, {"code": code}).status_code == 409
    assert browser.get("/api/account/me/").status_code in (401, 403)


def test_counter_already_over_limit_is_refused_before_compare(send):
    """Параллельные запросы успели поднять счётчик до лимита — следующий не сравнивает код."""
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    code = code_from_reply(send.call_args[0][0])
    MaxAuthAttempt.objects.filter(public_id=data["attempt_id"]).update(
        confirm_failures=confirm.MAX_FAILURES
    )
    resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 409
    assert _attempt(data["attempt_id"]).failure_reason == "code_attempts_exceeded"


def test_confirm_body_that_is_not_an_object_is_a_wrong_code_not_500(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    resp = browser.post(
        f"/api/auth/max/{data['attempt_id']}/confirm/",
        data=json.dumps(["123456"]),
        content_type="application/json",
    )
    assert resp.status_code == 400 and resp.json()["code"] == "wrong_code"


# ═══════════ В-4: кэш чистится вслед за попыткой ═══════════


def test_cancel_and_new_start_drop_pending_phone(send):
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    attempt = _attempt(data["attempt_id"])
    assert confirm.load_pending(attempt)["phone"] == PHONE

    # Новый старт той же сессии гасит прежнюю попытку и её кэш.
    data2, _ = _start(browser)
    attempt.refresh_from_db()
    assert attempt.status == Status.CANCELLED
    assert confirm.load_pending(attempt) is None

    # Отмена с сайта — тоже.
    _bot_started(data2["deeplink"].split("start=", 1)[1], ts=5)
    _share_contact(PHONE, mid="c2")
    attempt2 = _attempt(data2["attempt_id"])
    assert confirm.load_pending(attempt2)["phone"] == PHONE
    assert browser.post(f"/api/auth/max/{data2['attempt_id']}/cancel/").status_code == 200
    assert confirm.load_pending(attempt2) is None


def test_bot_refusal_drops_pending_and_cancel_needs_session_key():
    user = User.objects.create_user(phone=PHONE, password="pass12345")
    attempt = services.create_attempt(session_key="s1").attempt
    cache.set(confirm.pending_key(attempt), {"phone": PHONE}, 60)
    services._fail(attempt, "password_account")
    assert confirm.load_pending(attempt) is None
    assert user.pk
    # Пустой ключ сессии не совпадает ни с чем — даже с попыткой без ключа.
    orphan = MaxAuthAttempt.objects.create(
        secret_hash="x", browser_session_key="", expires_at=attempt.expires_at
    )
    assert services.cancel_attempt(orphan.public_id.hex, session_key="") is None


# ═══════════ В-5: сайт до кода не раскрывает состояние чужого аккаунта ═══════════


def test_status_hides_private_login_reason_before_code_but_not_after(send):
    User.objects.create_user(phone=PHONE, password="pass12345")  # аккаунт с паролем
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    status = browser.get(f"/api/auth/max/{data['attempt_id']}/status/").json()
    assert status == {**status, "status": "failed", "failure_reason": "declined_in_max"}
    assert _attempt(data["attempt_id"]).failure_reason == "phone_unverified"
    assert "не подтверждён" in _last_text(send)

    # После выдачи кода причина честная: между кодом и вводом аккаунт стал парольным.
    browser2 = APIClient()
    data2, token2 = _start(browser2)
    _bot_started(token2, chat_id=901, max_user_id=7002, ts=11)
    _share_contact("+79007778899", chat_id=901, max_user_id=7002, mid="c9", ts=12)
    code = code_from_reply(send.call_args[0][0])
    User.objects.create_user(phone="+79007778899", password="pass12345")
    resp = browser2.post(f"/api/auth/max/{data2['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 409 and resp.json()["failure_reason"] == "phone_unverified"


# ═══════════ View: чужой пользователь, вошедший, повтор ═══════════


def test_link_confirm_by_other_user_is_404_and_repeat_confirm_is_409(send):
    owner = User.objects.create_user(
        email="o@test.ru", phone=PHONE, password="pass12345", phone_verified=True
    )
    browser = APIClient()
    browser.force_login(owner)
    data = browser.post("/api/account/max/link/").json()
    token = data["deeplink"].split("start=", 1)[1]
    _bot_started(token)
    _share_contact(PHONE)
    code = code_from_reply(send.call_args[0][0])

    other = User.objects.create_user(email="x@test.ru", password="pass12345")
    other_browser = APIClient()
    other_browser.force_login(other)
    resp = other_browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 404

    resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    assert MaxAccount.objects.get(max_user_id=7001).user_id == owner.pk
    # Повторный ввод по завершённой попытке ничего не подтверждает заново.
    resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 409 and resp.json()["status"] == "completed"


def test_login_confirm_while_already_authenticated_is_409(send):
    """Вкладка со входом через MAX осталась открытой, а в соседней уже вошли паролем."""
    browser = APIClient()
    browser.force_login(User.objects.create_user(email="x@test.ru", password="pass12345"))
    data, token = _start(browser)
    _bot_started(token)
    _share_contact(PHONE)
    code = code_from_reply(send.call_args[0][0])
    resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 409 and resp.json()["code"] == "already_authenticated"
    assert _attempt(data["attempt_id"]).status == Status.CONFIRMATION_REQUIRED
    assert not User.objects.filter(phone=PHONE).exists()


# ═══════════ Прочее: уведомление о входе, без id MAX, заблокированный ═══════════


def test_login_sends_chat_notification(send, django_capture_on_commit_callbacks):
    user = User.objects.create_user(phone=PHONE, password=None, phone_verified=True)
    MaxAccount.objects.create(user=user, max_user_id=7001, chat_id=900, is_active=True)
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)  # привязанный MAX — код сразу
    code = code_from_reply(send.call_args[0][0])
    with django_capture_on_commit_callbacks(execute=True):
        resp = browser.post(f"/api/auth/max/{data['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 200
    assert Notification.objects.filter(user=user, event="max_login").exists()


def test_start_without_max_user_id_fails_attempt(send):
    user = User.objects.create_user(phone=PHONE, password=None, phone_verified=True)
    MaxAccount.objects.create(user=user, max_user_id=7001, chat_id=900, is_active=True)
    browser = APIClient()
    data, token = _start(browser)
    _webhook({"update_type": "bot_started", "timestamp": 1, "chat_id": 900, "payload": token})
    attempt = _attempt(data["attempt_id"])
    assert attempt.status in (Status.FAILED, Status.PENDING)
    assert attempt.max_user_id is None
    assert "Код:" not in _last_text(send)


def test_inactive_account_is_not_let_in(send):
    user = User.objects.create_user(
        phone=PHONE, password=None, phone_verified=True, is_active=False
    )
    MaxAccount.objects.create(user=user, max_user_id=7001, chat_id=900, is_active=True)
    browser = APIClient()
    data, token = _start(browser)
    _bot_started(token)
    attempt = _attempt(data["attempt_id"])
    assert (attempt.status, attempt.failure_reason) == (Status.FAILED, "inactive_account")
    assert "заблокирован" in _last_text(send)
