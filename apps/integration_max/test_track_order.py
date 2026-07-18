"""Тесты «Отслеживать заказ в MAX» для гостя без аккаунта (#520).

Узкий грант (OrderTrackingGrant): один заказ → один MAX chat_id, без создания
User/входа/claim_guest_orders (см. Security constraints тикета — авто-слияние
аккаунтов запрещено). Покрывает AC: нельзя подписаться на чужой заказ,
phone mismatch не связывает и не раскрывает заказ, повтор CTA идемпотентен,
security-тесты на replay/enumeration/cross-user access.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import SiteSettings

from . import services
from .models import MaxAuthAttempt, OrderTrackingGrant
from .tests import TOKEN, _make_vcf_payload

MAX_SETTINGS = {"MAX_BOT_TOKEN": "test-token", "MAX_BOT_API_URL": "https://test.max.ru"}

Status = MaxAuthAttempt.Status
Operation = MaxAuthAttempt.Operation
ORDER_PHONE = "+79001234567"
OTHER_PHONE = "+79009998877"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def _enable_max(db):
    s = SiteSettings.get_solo()
    s.max_chat_enabled = True
    s.save()


@pytest.fixture
def product(db):
    from apps.catalog.models import Product, ProductStatus

    return Product.objects.create(
        name="Дрель",
        slug="drel-track-520",
        price=Decimal("1000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=10,
        available_quantity=10,
    )


@pytest.fixture
def guest_order(db, product):
    """Реальный гостевой заказ через публичный API — order_number + access_token."""
    guest = APIClient()
    guest.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest.post(
        "/api/orders/",
        {"customer_name": "Гость", "customer_phone": ORDER_PHONE},
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    from apps.orders.models import Order

    return Order.objects.get(order_number=data["order_number"]), data["access_token"]


def _track_attempt(order, session="sess-track-1"):
    return services.create_attempt(
        session_key=session, operation_type=Operation.TRACK_ORDER, order=order
    ).attempt


# ═══════════ Сервисный слой: complete_from_contact / TRACK_ORDER ═══════════


@pytest.mark.django_db
def test_matching_phone_creates_grant(guest_order):
    order, _token = guest_order
    attempt = _track_attempt(order)
    res = services.complete_from_contact(attempt, max_user_id=6001, phone=ORDER_PHONE, chat_id=777)
    assert res.status == Status.COMPLETED
    grant = OrderTrackingGrant.objects.get(order=order)
    assert grant.max_user_id == 6001 and grant.chat_id == 777


@pytest.mark.django_db
def test_phone_mismatch_denied_without_leaking_order(guest_order):
    """AC: phone mismatch не связывает заказ и не раскрывает его данные —
    отказ generic (без номера заказа/имени/суммы в failure_reason)."""
    order, _token = guest_order
    attempt = _track_attempt(order)
    res = services.complete_from_contact(attempt, max_user_id=6002, phone=OTHER_PHONE, chat_id=778)
    assert res.status == Status.FAILED
    assert res.failure_reason == "phone_mismatch"
    assert not OrderTrackingGrant.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_no_target_order_fails_cleanly():
    """Дефолтный сценарий (нет order на попытке) — не должен упасть с исключением."""
    attempt = services.create_attempt(
        session_key="sess-no-order", operation_type=Operation.TRACK_ORDER
    ).attempt
    res = services.complete_from_contact(attempt, max_user_id=6003, phone=ORDER_PHONE)
    assert res.status == Status.FAILED and res.failure_reason == "no_target_order"


@pytest.mark.django_db
def test_repeat_completion_is_idempotent(guest_order):
    """AC: повтор CTA идемпотентен — повторная доставка контакта не плодит гранты."""
    order, _token = guest_order
    attempt = _track_attempt(order)
    services.complete_from_contact(attempt, max_user_id=6004, phone=ORDER_PHONE, chat_id=779)
    attempt.refresh_from_db()
    services.complete_from_contact(attempt, max_user_id=6004, phone=ORDER_PHONE, chat_id=779)
    assert OrderTrackingGrant.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_expired_attempt_cannot_grant(guest_order):
    order, _token = guest_order
    attempt = _track_attempt(order)
    MaxAuthAttempt.objects.filter(pk=attempt.pk).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    attempt.refresh_from_db()
    res = services.complete_from_contact(attempt, max_user_id=6005, phone=ORDER_PHONE)
    assert res.status in (Status.EXPIRED, Status.FAILED)
    assert not OrderTrackingGrant.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_grant_does_not_create_account_or_claim_orders(guest_order):
    """Ключевое architectural-решение (#520): узкий грант, БЕЗ создания User,
    БЕЗ claim_guest_orders — заказ остаётся user=None."""
    from django.contrib.auth import get_user_model

    order, _token = guest_order
    attempt = _track_attempt(order)
    services.complete_from_contact(attempt, max_user_id=6006, phone=ORDER_PHONE, chat_id=780)
    order.refresh_from_db()
    assert order.user is None
    User = get_user_model()
    assert not User.objects.filter(phone=ORDER_PHONE).exists()


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_snapshot_notification_sent_once_after_grant(
    mock_send_message, guest_order, django_capture_on_commit_callbacks
):
    """Scope: разовое сообщение с текущим статусом сразу после выдачи гранта."""
    from apps.notifications.models import NotificationLog

    order, _token = guest_order
    attempt = _track_attempt(order)
    with django_capture_on_commit_callbacks(execute=True):
        services.complete_from_contact(attempt, max_user_id=6007, phone=ORDER_PHONE, chat_id=781)
    logs = NotificationLog.objects.filter(idempotency_key=f"track-order-connected-{order.pk}")
    assert logs.count() == 1
    log = logs.first()
    assert log.chat_id == 781 and log.user is None
    mock_send_message.assert_called_once_with(781, mock.ANY)


# ═══════════ API: старт/статус, cross-order/cross-session security ═══════════


@pytest.mark.django_db
def test_track_start_requires_valid_token(api, guest_order):
    order, token = guest_order
    assert api.post(f"/api/orders/{order.order_number}/max-track/start/", {}).status_code == 404
    resp = api.post(
        f"/api/orders/{order.order_number}/max-track/start/",
        {"access_token": "wrong-token"},
        format="json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_track_start_rejects_token_of_another_order(api, product, guest_order):
    """AC: нельзя подписаться на чужой заказ — токен заказа A не работает для номера заказа B."""
    order_a, token_a = guest_order
    guest_b = APIClient()
    guest_b.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    create_b = guest_b.post(
        "/api/orders/", {"customer_name": "Гость Б", "customer_phone": OTHER_PHONE}, format="json"
    )
    number_b = create_b.json()["order_number"]

    # Токен заказа A + номер заказа Б — не должно сработать (перебор номеров).
    resp = api.post(
        f"/api/orders/{number_b}/max-track/start/",
        {"access_token": token_a},
        format="json",
    )
    assert resp.status_code == 404
    assert not MaxAuthAttempt.objects.filter(order__order_number=number_b).exists()


@pytest.mark.django_db
def test_track_start_success_returns_deeplink_without_pii(api, guest_order):
    order, token = guest_order
    resp = api.post(
        f"/api/orders/{order.order_number}/max-track/start/",
        {"access_token": token},
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert ORDER_PHONE not in data["deeplink"]
    assert order.order_number not in data["deeplink"]
    attempt = MaxAuthAttempt.objects.get(public_id=data["attempt_id"])
    assert attempt.operation_type == Operation.TRACK_ORDER and attempt.order_id == order.pk


@pytest.mark.django_db
def test_track_status_scoped_to_creating_session(api, guest_order):
    order, token = guest_order
    start = api.post(
        f"/api/orders/{order.order_number}/max-track/start/",
        {"access_token": token},
        format="json",
    ).json()
    attempt = MaxAuthAttempt.objects.get(public_id=start["attempt_id"])
    services.complete_from_contact(attempt, max_user_id=6010, phone=ORDER_PHONE, chat_id=782)

    # Чужая сессия — 404, не может прочитать статус чужой попытки.
    other = APIClient()
    assert other.get(f"/api/orders/max-track/{start['attempt_id']}/status/").status_code == 404

    resp = api.get(f"/api/orders/max-track/{start['attempt_id']}/status/")
    assert resp.status_code == 200 and resp.json()["status"] == "completed"


@pytest.mark.django_db
def test_track_status_does_not_log_in_guest(api, guest_order):
    """В отличие от MaxAuthStatusView — track_order НЕ поднимает сессию (гость остаётся гостем)."""
    order, token = guest_order
    start = api.post(
        f"/api/orders/{order.order_number}/max-track/start/",
        {"access_token": token},
        format="json",
    ).json()
    attempt = MaxAuthAttempt.objects.get(public_id=start["attempt_id"])
    services.complete_from_contact(attempt, max_user_id=6011, phone=ORDER_PHONE, chat_id=783)
    api.get(f"/api/orders/max-track/{start['attempt_id']}/status/")
    assert api.get("/api/account/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_track_status_rejects_regular_login_attempt_id(api):
    """Cross-endpoint enumeration: id обычной LOGIN-попытки не должен приниматься
    track-order-статусом (разные operation_type)."""
    start = api.post("/api/auth/max/start/").json()
    resp = api.get(f"/api/orders/max-track/{start['attempt_id']}/status/")
    assert resp.status_code == 404


# ═══════════ e2e через webhook ═══════════


@mock.patch("apps.integration_max.webhook._send_reply")
def _run_webhook_flow(api, order, token, phone, mock_send):
    with override_settings(MAX_BOT_TOKEN=TOKEN, MAX_WEBHOOK_SECRET="wh-secret"):
        start = api.post(
            f"/api/orders/{order.order_number}/max-track/start/",
            {"access_token": token},
            format="json",
        ).json()
        deeplink_token = start["deeplink"].split("start=", 1)[1]
        hdr = {"HTTP_X_MAX_WEBHOOK_SECRET": "wh-secret"}

        api.post(
            "/api/max/webhook/",
            data=json.dumps(
                {
                    "update_type": "bot_started",
                    "timestamp": 1,
                    "chat_id": 950,
                    "user": {"user_id": 7001},
                    "payload": deeplink_token,
                }
            ),
            content_type="application/json",
            **hdr,
        )
        vcf = _make_vcf_payload(phone, TOKEN)
        api.post(
            "/api/max/webhook/",
            data=json.dumps(
                {
                    "update_type": "message_created",
                    "timestamp": 2,
                    "message": {
                        "sender": {"user_id": 7001},
                        "recipient": {"chat_id": 950, "chat_type": "dialog"},
                        "body": {
                            "mid": "c-track-1",
                            "attachments": [{"type": "contact", "payload": vcf}],
                        },
                    },
                }
            ),
            content_type="application/json",
            **hdr,
        )
        return MaxAuthAttempt.objects.get(public_id=start["attempt_id"])


@pytest.mark.django_db
def test_e2e_track_order_matching_phone_via_webhook(api, guest_order):
    order, token = guest_order
    attempt = _run_webhook_flow(api, order, token, ORDER_PHONE)
    assert attempt.status == Status.COMPLETED
    assert OrderTrackingGrant.objects.filter(order=order, chat_id=950).exists()


@pytest.mark.django_db
def test_e2e_track_order_phone_mismatch_via_webhook(api, guest_order):
    order, token = guest_order
    attempt = _run_webhook_flow(api, order, token, OTHER_PHONE)
    assert attempt.status == Status.FAILED
    assert attempt.failure_reason == "phone_mismatch"
    assert not OrderTrackingGrant.objects.filter(order=order).exists()
