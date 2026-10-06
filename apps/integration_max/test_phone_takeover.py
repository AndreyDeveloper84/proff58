"""DRF-2735: чужой неподтверждённый номер в аккаунте ничего не даёт.

Сценарий атаки, который раньше проходил целиком через публичный API:
A регистрируется по e-mail и вписывает себе номер V («Сменить телефон» — любой
свободный номер, нужен только свой пароль). V жмёт «Войти через MAX» → попадал в
аккаунт A, а A получал ``phone_verified`` и при следующем входе паролем забирал
гостевые заказы V. Без входа то же делал старый поток бота по коду.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.orders.models import Order

from .handlers import auth, auth_flow
from .models import MaxAccount, MaxAuthAttempt
from .tests import TOKEN, _make_vcf_payload, code_from_reply

User = get_user_model()
Status = MaxAuthAttempt.Status

VICTIM_PHONE = "+79001234567"
ATTACKER = {"email": "attacker@test.ru", "password": "Str0ng-Pass-2026"}
HDR = {"HTTP_X_MAX_BOT_API_SECRET": "wh-secret"}


@pytest.fixture(autouse=True)
def _max_settings(settings):
    settings.MAX_BOT_TOKEN = TOKEN
    settings.MAX_BOT_USERNAME = "test_auth_bot"
    settings.MAX_WEBHOOK_SECRET = "wh-secret"
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def attacker_browser(db):
    """A зарегистрировался по e-mail и вписал себе номер жертвы — публичным API."""
    browser = APIClient()
    assert browser.post("/api/account/register/", ATTACKER, format="json").status_code in (200, 201)
    resp = browser.post(
        "/api/account/change-phone/",
        {"new_phone": VICTIM_PHONE, "password": ATTACKER["password"]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    browser.post("/api/account/logout/")
    return browser


@pytest.fixture
def guest_order(db):
    """Гостевой заказ жертвы — то, что A хотел забрать себе."""
    return Order.objects.create(order_number="G-VICTIM", customer_phone=VICTIM_PHONE)


def _webhook(data: dict):
    return APIClient().post(
        "/api/max/webhook/", data=json.dumps(data), content_type="application/json", **HDR
    )


def _bot_started(token: str | None, *, chat_id: int = 900, max_user_id: int = 7001, ts: int = 1):
    data = {
        "update_type": "bot_started",
        "timestamp": ts,
        "chat_id": chat_id,
        "user": {"user_id": max_user_id},
    }
    if token is not None:
        data["payload"] = token
    return _webhook(data)


def _share_contact(phone: str, *, chat_id: int = 900, max_user_id: int = 7001, mid: str = "c1"):
    return _webhook(
        {
            "update_type": "message_created",
            "timestamp": 2,
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


def _text(text: str, *, chat_id: int = 900, mid: str = "t1"):
    return _webhook(
        {
            "update_type": "message_created",
            "timestamp": 3,
            "message": {
                "sender": {"user_id": 7001},
                "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
                "body": {"mid": mid, "text": text},
            },
        }
    )


def _assert_attacker_got_nothing(attacker_browser, guest_order):
    """A входит паролем: ни заказа жертвы, ни флага, ни привязки её MAX."""
    resp = attacker_browser.post("/api/account/login/", ATTACKER, format="json")
    assert resp.status_code == 200
    assert "claimed_orders" not in resp.json()
    guest_order.refresh_from_db()
    assert guest_order.user_id is None
    account = User.objects.get(email=ATTACKER["email"])
    assert account.phone_verified is False
    assert account.max_chat_id is None
    assert not MaxAccount.objects.exists()
    assert attacker_browser.get("/api/orders/").json()["count"] == 0


@mock.patch("apps.integration_max.webhook._send_reply")
def test_victim_login_via_max_does_not_enter_attacker_account(
    mock_send, attacker_browser, guest_order
):
    victim = APIClient()
    start = victim.post("/api/auth/max/start/").json()
    token = start["deeplink"].split("start=", 1)[1]

    _bot_started(token)
    _share_contact(VICTIM_PHONE)

    # Бот объясняет отказ, а не присылает код.
    reply = mock_send.call_args[0][0]["text"]
    assert "не подтверждён" in reply and "Код:" not in reply

    status = victim.get(f"/api/auth/max/{start['attempt_id']}/status/").json()
    # Сайту причина не раскрывается: до кода её читает и чужой браузер (есть ли у
    # номера аккаунт и какой). Честная причина — в чате бота и в БД.
    assert (status["status"], status["failure_reason"]) == ("failed", "declined_in_max")
    assert MaxAuthAttempt.objects.get(public_id=start["attempt_id"]).failure_reason == (
        "phone_unverified"
    )
    assert victim.get("/api/account/me/").status_code in (401, 403)
    assert User.objects.count() == 1  # нового аккаунта на занятый номер тоже нет

    _assert_attacker_got_nothing(attacker_browser, guest_order)


@mock.patch("apps.integration_max.webhook._send_reply")
def test_second_contact_after_refusal_changes_nothing(mock_send, attacker_browser, guest_order):
    """Жертва жмёт «Поделиться номером» ещё раз: попытка уже закрыта, номер уходит
    «в никуда» — раньше здесь подхватывал старый поток по коду."""
    victim = APIClient()
    start = victim.post("/api/auth/max/start/").json()
    _bot_started(start["deeplink"].split("start=", 1)[1])
    _share_contact(VICTIM_PHONE, mid="c1")

    _share_contact(VICTIM_PHONE, mid="c2")
    assert mock_send.call_args[0][0]["text"] == auth.STALE_LINK_TEXT
    _text("1234")
    assert mock_send.call_args[0][0]["text"] == auth.HELP_TEXT

    assert cache.get("max_otp:900") is None
    _assert_attacker_got_nothing(attacker_browser, guest_order)


@mock.patch("apps.integration_max.webhook._send_reply")
def test_contact_after_expired_attempt_changes_nothing(mock_send, attacker_browser, guest_order):
    from django.utils import timezone

    victim = APIClient()
    start = victim.post("/api/auth/max/start/").json()
    _bot_started(start["deeplink"].split("start=", 1)[1])
    MaxAuthAttempt.objects.filter(public_id=start["attempt_id"]).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )

    _share_contact(VICTIM_PHONE)

    # Раньше истёкшая попытка отдавала контакт старому потоку: бот находил аккаунт
    # по номеру и показывал код. Теперь — только «ссылка не действует».
    assert mock_send.call_args[0][0]["text"] == auth.STALE_LINK_TEXT
    assert MaxAuthAttempt.objects.get(public_id=start["attempt_id"]).status == Status.EXPIRED
    assert cache.get("max_otp:900") is None
    _assert_attacker_got_nothing(attacker_browser, guest_order)


@mock.patch("apps.integration_max.webhook._send_reply")
def test_old_bot_flow_no_longer_verifies_the_number(mock_send, attacker_browser, guest_order):
    """Жертва просто открыла бота: «Старт» без ссылки → номер → цифры."""
    _bot_started(None)
    assert "request_contact" not in json.dumps(mock_send.call_args[0][0])
    _share_contact(VICTIM_PHONE)
    # Кода нет: бот его не выдал и нигде не запомнил, подбирать нечего.
    assert mock_send.call_args[0][0]["text"] == auth.STALE_LINK_TEXT
    assert cache.get("max_otp:900") is None
    _text("0000")
    assert mock_send.call_args[0][0]["text"] == auth.HELP_TEXT

    _assert_attacker_got_nothing(attacker_browser, guest_order)


# ═══════════ Старая ссылка ═══════════


@pytest.mark.parametrize(
    "status", [Status.COMPLETED, Status.FAILED, Status.CANCELLED, Status.EXPIRED]
)
@mock.patch("apps.integration_max.webhook._send_reply")
def test_stale_deeplink_does_not_hijack_live_attempt(mock_send, db, status):
    """Ссылка закрытой попытки не перебивает в чате новую живую: контакт, присланный
    следом, завершает живую попытку, а не уходит в «ссылка не действует»."""
    old = APIClient().post("/api/auth/max/start/").json()
    MaxAuthAttempt.objects.filter(public_id=old["attempt_id"]).update(status=status)
    live_browser = APIClient()
    live = live_browser.post("/api/auth/max/start/").json()

    _bot_started(live["deeplink"].split("start=", 1)[1], ts=1)
    assert "request_contact" in json.dumps(mock_send.call_args[0][0])

    _bot_started(old["deeplink"].split("start=", 1)[1], ts=2)
    assert mock_send.call_args[0][0]["text"] == auth.STALE_LINK_TEXT

    _share_contact(VICTIM_PHONE)
    live_attempt = MaxAuthAttempt.objects.get(public_id=live["attempt_id"])
    assert live_attempt.status == Status.CONFIRMATION_REQUIRED  # живая попытка получила код
    assert MaxAuthAttempt.objects.get(public_id=old["attempt_id"]).status == status


@mock.patch("apps.integration_max.webhook._send_reply")
def test_stale_deeplink_does_not_issue_a_code(mock_send, db):
    """MAX уже привязан: по закрытой попытке бот раньше отвечал «Вход подтверждён»,
    теперь не должен и код выдавать."""
    owner = User.objects.create_user(phone=VICTIM_PHONE, password=None, phone_verified=True)
    MaxAccount.objects.create(user=owner, max_user_id=7001, chat_id=900, phone=VICTIM_PHONE)
    old = APIClient().post("/api/auth/max/start/").json()
    MaxAuthAttempt.objects.filter(public_id=old["attempt_id"]).update(status=Status.COMPLETED)

    _bot_started(old["deeplink"].split("start=", 1)[1])

    assert mock_send.call_args[0][0]["text"] == auth.STALE_LINK_TEXT


# ═══════════ Привязка из кабинета ═══════════


@mock.patch("apps.integration_max.webhook._send_reply")
def test_link_names_the_account_and_does_not_verify_the_number(
    mock_send, attacker_browser, guest_order
):
    """A начинает привязку у себя и пересылает ссылку жертве. Бот называет аккаунт —
    жертва может заметить, что он не её. Поделилась номером — всё равно ничего не
    привязано, пока код из бота не введён в браузере A (DRF-2740)."""
    attacker_browser.post("/api/account/login/", ATTACKER, format="json")
    start = attacker_browser.post("/api/account/max/link/").json()
    token = start["deeplink"].split("start=", 1)[1]

    _bot_started(token)
    consent = mock_send.call_args[0][0]["text"]
    assert "a•••@test.ru" in consent
    assert "не делитесь номером" in consent
    assert ATTACKER["email"] not in consent  # адрес целиком не раскрываем

    _share_contact(VICTIM_PHONE)
    reply = mock_send.call_args[0][0]
    # DRF-2740: привязка не завершается в боте — жертве приходит код с именем аккаунта
    # и последствием; без ввода кода в браузере A ничего не привязано.
    assert "a•••@test.ru" in reply["text"] and "входить от вашего имени" in reply["text"]
    assert not MaxAccount.objects.exists()
    # A выманил код и ввёл его у себя — только тогда MAX жертвы привязан (остаточный
    # риск, равный коду из SMS); номер подтверждённым при этом не становится.
    code = code_from_reply(reply)
    resp = attacker_browser.post(f"/api/auth/max/{start['attempt_id']}/confirm/", {"code": code})
    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    assert MaxAccount.objects.filter(user__email=ATTACKER["email"]).exists()

    account = User.objects.get(email=ATTACKER["email"])
    assert account.phone_verified is False
    attacker_browser.post("/api/account/logout/")
    resp = attacker_browser.post("/api/account/login/", ATTACKER, format="json")
    assert "claimed_orders" not in resp.json()
    guest_order.refresh_from_db()
    assert guest_order.user_id is None


@mock.patch("apps.integration_max.webhook._send_reply")
def test_link_refusal_does_not_blame_the_number(mock_send, attacker_browser):
    """К аккаунту уже подключён другой MAX: проверка идёт до сверки номера, и текст
    «аккаунт с этим номером» при привязке был бы неправдой — аккаунт выбран в кабинете."""
    account = User.objects.get(email=ATTACKER["email"])
    MaxAccount.objects.create(user=account, max_user_id=5555, phone="+79005550000")
    attacker_browser.post("/api/account/login/", ATTACKER, format="json")
    start = attacker_browser.post("/api/account/max/link/").json()

    _bot_started(start["deeplink"].split("start=", 1)[1])

    # DRF-2740: отказ — сразу на «Начать», номер у человека даже не спрашивают.
    reply = mock_send.call_args[0][0]
    assert "К этому аккаунту уже подключён другой MAX" in reply["text"]
    assert "с этим номером" not in reply["text"]
    assert "request_contact" not in json.dumps(reply)
    status = attacker_browser.get(f"/api/auth/max/{start['attempt_id']}/status/").json()
    assert (status["status"], status["failure_reason"]) == ("failed", "user_has_other_max")


@pytest.mark.parametrize(
    ("email", "phone", "expected"),
    [
        ("ivan@mail.ru", "+79001112233", "i•••@mail.ru"),
        ("", "+79001112233", "с номером •••2233"),
        ("", "", "без e-mail"),
    ],
)
def test_account_label_masks_identity(email, phone, expected):
    user = User(email=email, phone=phone or None)
    assert auth_flow.account_label(user) == expected
