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
from .models import MaxAccount
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
    # «Старт» без ссылки с сайта: объясняем, как войти, номер не просим (DRF-2735).
    assert reply["text"] == auth.HELP_TEXT
    assert "request_contact" not in json.dumps(reply)


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


# ═══════════ БОТ ВНЕ ПОПЫТКИ (DRF-2735) ═══════════
#
# Старый поток привязки по коду удалён: бот по номеру из контакта находил аккаунт
# и после «кода», который сам же показывал, писал max_chat_id и phone_verified.
# Чужой номер, вписанный в профиль, так «подтверждался» первым же владельцем
# номера, открывшим бота. Теперь без живой попытки с сайта бот по номеру никого
# не ищет и ничего не пишет.

HDR = {"HTTP_X_MAX_BOT_API_SECRET": "my-secret"}


def _contact_message(phone: str, timestamp: int, chat_id: int = 500) -> str:
    return json.dumps(
        {
            "update_type": "message_created",
            "timestamp": timestamp,
            "message": {
                "sender": {"user_id": 99},
                "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
                "body": {
                    "mid": f"c{timestamp}",
                    "attachments": [
                        {"type": "contact", "payload": _make_vcf_payload(phone, TOKEN)}
                    ],
                },
            },
        }
    )


def _post(client, data: str):
    return client.post("/api/max/webhook/", data=data, content_type="application/json", **HDR)


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="my-secret")
@pytest.mark.django_db
@mock.patch("apps.integration_max.webhook._send_reply")
def test_contact_without_attempt_touches_nothing(mock_send, client, user):
    """«Старт» без ссылки → номер → цифры: аккаунт с этим номером не тронут."""
    _post(
        client,
        json.dumps({"update_type": "bot_started", "timestamp": 5001, "chat_id": 500, "user": {}}),
    )
    assert mock_send.call_args[0][0]["text"] == auth.HELP_TEXT

    _post(client, _contact_message("+79001234567", 5002))
    assert mock_send.call_args[0][0]["text"] == auth.STALE_LINK_TEXT

    _post(client, _text_message("1234", 5003))
    assert mock_send.call_args[0][0]["text"] == auth.HELP_TEXT

    user.refresh_from_db()
    assert user.max_chat_id is None
    assert user.phone_verified is False
    assert not MaxAccount.objects.exists()
    assert cache.get("max_otp:500") is None


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="my-secret")
@pytest.mark.django_db
@mock.patch("apps.integration_max.webhook._send_reply")
def test_bot_started_with_unknown_token_says_link_is_stale(mock_send, client):
    _post(
        client,
        json.dumps(
            {
                "update_type": "bot_started",
                "timestamp": 5004,
                "chat_id": 501,
                "user": {"user_id": 99},
                "payload": "0" * 32 + ".not-a-secret",
            }
        ),
    )
    reply = mock_send.call_args[0][0]
    assert reply["text"] == auth.STALE_LINK_TEXT
    assert "request_contact" not in json.dumps(reply)


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="my-secret")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "token", ["garbage.secret", "abc.def", "не-uuid.x", "...", "a" * 500 + ".b"]
)
@mock.patch("apps.integration_max.webhook._send_reply")
def test_bot_started_with_malformed_token_does_not_crash(mock_send, client, token):
    """Параметр ``start`` диплинка задаёт кто угодно. Не-UUID раньше ронял вебхук
    (UUIDField бросает ValidationError, а ловился только ValueError) — бот молчал,
    а MAX получал 500 и повторял доставку."""
    resp = _post(
        client,
        json.dumps(
            {
                "update_type": "bot_started",
                "timestamp": 5005,
                "chat_id": 502,
                "user": {"user_id": 99},
                "payload": token,
            }
        ),
    )
    assert resp.status_code == 200
    reply = mock_send.call_args[0][0]
    assert reply["text"] in (auth.STALE_LINK_TEXT, auth.HELP_TEXT)
    assert "request_contact" not in json.dumps(reply)


def test_legacy_code_flow_is_gone():
    """Точек входа старого потока больше нет — случайно вернуть их нельзя."""
    for name in ("handle_otp_confirm", "generate_otp", "OTP_LENGTH"):
        assert not hasattr(auth, name), name


def _text_message(text: str, timestamp: int) -> str:
    return json.dumps(
        {
            "update_type": "message_created",
            "timestamp": timestamp,
            "message": {
                "sender": {"user_id": 99},
                "recipient": {"chat_id": 500, "chat_type": "dialog"},
                "body": {"mid": f"t{timestamp}", "text": text},
            },
        }
    )


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="my-secret")
@pytest.mark.django_db
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.parametrize("text", ["старт", "Здравствуйте, есть перфоратор?"])
def test_unknown_text_gets_help_reply(mock_send, client, text):
    # Раньше бот молчал на любой непонятный текст — выглядело как поломка.
    client.post(
        "/api/max/webhook/",
        data=_text_message(text, 6001),
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="my-secret",
    )

    mock_send.assert_called_once()
    reply = mock_send.call_args[0][0]
    assert reply["chat_id"] == 500
    assert reply["text"] == auth.HELP_TEXT


@override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="my-secret")
@pytest.mark.django_db
@mock.patch("apps.integration_max.webhook._send_reply")
@pytest.mark.parametrize("text", ["/start", "start", "Начать"])
def test_start_command_explains_how_to_login(mock_send, client, text):
    """Команда «старт» текстом — та же подсказка, что и кнопка без ссылки."""
    _post(client, _text_message(text, 6002))

    reply = mock_send.call_args[0][0]
    assert reply["text"] == auth.HELP_TEXT
    assert "request_contact" not in json.dumps(reply)
