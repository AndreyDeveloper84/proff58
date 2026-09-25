"""Тесты MAX webhook и auth handler (#47)."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, override_settings

from .handlers import auth
from .verify import extract_phone_from_vcf, verify_contact_hash

User = get_user_model()
TOKEN = "test-bot-token-12345"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass123")


def _make_vcf_payload(phone: str, token: str) -> dict:
    vcf = f"BEGIN:VCARD\r\nVERSION:3.0\r\nTEL;TYPE=cell:{phone.lstrip('+')}\r\nFN:Test\r\nEND:VCARD\r\n"
    vcf_escaped = vcf.replace("\r\n", "\\r\\n")
    h = hmac.new(token.encode(), vcf.encode(), hashlib.sha256).hexdigest()
    return {"vcf_info": vcf_escaped, "hash": h, "max_info": {"user_id": 99}}


# ═══════════ VERIFY ═══════════


def test_verify_valid():
    vcf = r"BEGIN:VCARD\r\nTEL;TYPE=cell:79001234567\r\nEND:VCARD\r\n"
    vcf_real = vcf.replace("\\r\\n", "\r\n")
    expected = hmac.new(TOKEN.encode(), vcf_real.encode(), hashlib.sha256).hexdigest()
    assert verify_contact_hash(TOKEN, vcf, expected) is True


def test_verify_invalid():
    assert verify_contact_hash(TOKEN, "vcf", "wrong") is False


def test_extract_phone():
    assert (
        extract_phone_from_vcf(r"BEGIN:VCARD\r\nTEL;TYPE=cell:79001234567\r\nEND:VCARD\r\n")
        == "+79001234567"
    )


# ═══════════ WEBHOOK ENDPOINT ═══════════


@pytest.mark.django_db
def test_webhook_rejects_get(client):
    assert client.get("/api/max/webhook/").status_code == 405


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
def test_webhook_rejects_invalid_json(client):
    resp = client.post(
        "/api/max/webhook/",
        data="bad",
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="my-secret",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
def test_webhook_rejects_wrong_secret(client):
    resp = client.post(
        "/api/max/webhook/",
        data=json.dumps({"update_type": "bot_started", "timestamp": 1, "chat_id": 1}),
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="wrong",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
def test_webhook_accepts_correct_secret(mock_send, client):
    resp = client.post(
        "/api/max/webhook/",
        data=json.dumps({"update_type": "bot_started", "timestamp": 2, "chat_id": 100, "user": {}}),
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="my-secret",
    )
    assert resp.status_code == 200
    mock_send.assert_called_once()


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
def test_webhook_fail_closed_without_secret_header(client):
    """#428 (M-04): без корректного секрета webhook отклоняет запрос (fail-closed)."""
    resp = client.post(
        "/api/max/webhook/",
        data=json.dumps({"update_type": "bot_started", "timestamp": 9, "chat_id": 1}),
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="")
def test_webhook_fail_closed_when_secret_unset(client):
    """#428 (M-04): пустой MAX_WEBHOOK_SECRET → webhook закрыт, а не открыт."""
    resp = client.post(
        "/api/max/webhook/",
        data=json.dumps({"update_type": "bot_started", "timestamp": 10, "chat_id": 1}),
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="anything",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
def test_webhook_bot_started(mock_send, client):
    resp = client.post(
        "/api/max/webhook/",
        data=json.dumps(
            {"update_type": "bot_started", "timestamp": 3, "chat_id": 12345, "user": {}}
        ),
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="my-secret",
    )
    assert resp.status_code == 200
    reply = mock_send.call_args[0][0]
    assert reply["chat_id"] == 12345
    assert "request_contact" in json.dumps(reply)


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
@mock.patch("apps.integration_max.webhook._send_reply")
def test_webhook_duplicate_ignored(mock_send, client):
    payload = json.dumps(
        {
            "update_type": "bot_started",
            "timestamp": 4,
            "chat_id": 12345,
            "user": {},
            "message": {"body": {"mid": "dup-1"}},
        }
    )
    headers = {"HTTP_X_MAX_BOT_API_SECRET": "my-secret"}
    client.post("/api/max/webhook/", data=payload, content_type="application/json", **headers)
    client.post("/api/max/webhook/", data=payload, content_type="application/json", **headers)
    assert mock_send.call_count == 1


@pytest.mark.django_db
@override_settings(MAX_WEBHOOK_SECRET="my-secret")
def test_webhook_rejects_oversized_body(client):
    """#428 (M-04): слишком большое тело отвергается (413)."""
    big = json.dumps({"update_type": "bot_started", "x": "A" * (70 * 1024)})
    resp = client.post(
        "/api/max/webhook/",
        data=big,
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="my-secret",
    )
    assert resp.status_code == 413


@override_settings(MAX_BOT_TOKEN="tok", MAX_WEBHOOK_SECRET="")
def test_config_check_requires_secret_when_max_active():
    """#428 (M-04): системная проверка ловит активный MAX без секрета."""
    from apps.integration_max.apps import _check_max_webhook_secret

    errors = _check_max_webhook_secret(None)
    assert any(e.id == "integration_max.E001" for e in errors)


@override_settings(MAX_BOT_TOKEN="tok", MAX_WEBHOOK_SECRET="s", MAX_BOT_USERNAME="test_bot")
def test_config_check_passes_with_secret():
    from apps.integration_max.apps import _check_max_webhook_secret

    assert _check_max_webhook_secret(None) == []


@override_settings(MAX_BOT_TOKEN="tok", MAX_WEBHOOK_SECRET="s", MAX_BOT_USERNAME="")
def test_config_check_requires_username_when_max_active():
    from apps.integration_max.apps import _check_max_webhook_secret

    errors = _check_max_webhook_secret(None)
    assert any(e.id == "integration_max.E002" for e in errors)


# ═══════════ AUTH FLOW ═══════════


@override_settings(MAX_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_contact_sends_otp(user):
    payload = _make_vcf_payload("+79001234567", TOKEN)
    reply = auth.handle_contact(100, payload)
    assert "clipboard" in json.dumps(reply)
    assert cache.get("max_otp:100") is not None


@override_settings(MAX_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_otp_confirm_links_user(user):
    payload = _make_vcf_payload("+79001234567", TOKEN)
    auth.handle_contact(200, payload)
    otp = cache.get("max_otp:200")["otp"]

    reply = auth.handle_otp_confirm(200, otp)
    assert "успешно привязан" in reply["text"]
    user.refresh_from_db()
    assert user.max_chat_id == 200
    assert cache.get("max_otp:200") is None


@override_settings(MAX_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_otp_wrong_code(user):
    payload = _make_vcf_payload("+79001234567", TOKEN)
    auth.handle_contact(300, payload)
    reply = auth.handle_otp_confirm(300, "0000")
    assert "Неверный код" in reply["text"]
    assert cache.get("max_otp:300")["attempts"] == 1


@pytest.mark.django_db
def test_otp_no_pending():
    reply = auth.handle_otp_confirm(999, "1234")
    assert "Нет ожидающей" in reply["text"]


@override_settings(MAX_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_otp_max_attempts_blocks(user):
    """После OTP_MAX_ATTEMPTS неверных попыток — блок и очистка из кэша."""
    payload = _make_vcf_payload("+79001234567", TOKEN)
    auth.handle_contact(400, payload)

    for _ in range(auth.OTP_MAX_ATTEMPTS):
        reply = auth.handle_otp_confirm(400, "0000")
    # Последняя попытка превышает лимит
    reply = auth.handle_otp_confirm(400, "0000")
    assert "Превышено" in reply["text"]
    assert cache.get("max_otp:400") is None  # кэш очищен


@override_settings(MAX_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_otp_expired_shows_no_pending(user):
    """Истёкший OTP (кэш удалён по TTL) — «Нет ожидающей привязки»."""
    payload = _make_vcf_payload("+79001234567", TOKEN)
    auth.handle_contact(500, payload)
    # Симулируем истечение TTL — удаляем ключ вручную
    cache.delete("max_otp:500")
    reply = auth.handle_otp_confirm(500, "9999")
    assert "Нет ожидающей" in reply["text"]


@override_settings(MAX_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_contact_already_linked(user):
    User.objects.filter(pk=user.pk).update(max_chat_id=100)
    payload = _make_vcf_payload("+79001234567", TOKEN)
    reply = auth.handle_contact(100, payload)
    assert "уже привязан" in reply["text"]


# ═══════════ E2E ═══════════


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="my-secret")
@pytest.mark.django_db
@mock.patch("apps.integration_max.webhook._send_reply")
def test_e2e_auth_flow(mock_send, client, user):
    hdr = {"HTTP_X_MAX_BOT_API_SECRET": "my-secret"}
    # 1. bot_started
    client.post(
        "/api/max/webhook/",
        data=json.dumps(
            {"update_type": "bot_started", "timestamp": 5001, "chat_id": 500, "user": {}}
        ),
        content_type="application/json",
        **hdr,
    )

    # 2. contact
    vcf_payload = _make_vcf_payload("+79001234567", TOKEN)
    client.post(
        "/api/max/webhook/",
        data=json.dumps(
            {
                "update_type": "message_created",
                "timestamp": 5002,
                "message": {
                    "sender": {"user_id": 99},
                    "recipient": {"chat_id": 500, "chat_type": "dialog"},
                    "body": {
                        "mid": "m1",
                        "attachments": [{"type": "contact", "payload": vcf_payload}],
                    },
                },
            }
        ),
        content_type="application/json",
        **hdr,
    )
    otp = cache.get("max_otp:500")["otp"]

    # 3. OTP
    client.post(
        "/api/max/webhook/",
        data=json.dumps(
            {
                "update_type": "message_created",
                "timestamp": 5003,
                "message": {
                    "sender": {"user_id": 99},
                    "recipient": {"chat_id": 500, "chat_type": "dialog"},
                    "body": {"mid": "m2", "text": otp},
                },
            }
        ),
        content_type="application/json",
        **hdr,
    )

    assert mock_send.call_count == 3
    confirm_reply = mock_send.call_args[0][0]
    assert "успешно привязан" in confirm_reply["text"]
    user.refresh_from_db()
    assert user.max_chat_id == 500
