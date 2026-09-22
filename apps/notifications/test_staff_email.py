"""Письма сотрудникам через outbox (DRF-2296): постановка, дедуп, доставка,
классификация SMTP-ошибок, снимок получателей, команда проверки транспорта."""

from __future__ import annotations

import smtplib
from io import StringIO
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from .channels import PermanentChannelError, RetryableChannelError
from .channels import email as email_channel
from .models import NotificationChannel, NotificationErrorKind, NotificationLog, NotificationStatus
from .services import notify_staff
from .tasks import send_notification_task

PAYLOAD = {
    "order_number": "П-1",
    "created_at": "22.09.2026 10:00",
    "customer": "Иван",
    "customer_phone": "+79990000000",
    "total": "1000.00",
    "currency": "RUB",
    "items_count": 1,
    "delivery": "самовывоз",
    "payment": "наличными",
    "admin_url": "https://proff58.ru/admin/orders/order/1/change/",
}


@pytest.fixture
def получатели(settings):
    settings.STAFF_NOTIFICATION_EMAILS = ["m1@example.com", "m2@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"


# ═══════════ постановка в outbox ═══════════


@pytest.mark.django_db
def test_без_получателей_пишется_skipped_и_ничего_не_уходит(settings):
    settings.STAFF_NOTIFICATION_EMAILS = []
    log = notify_staff(event="staff_order_created", payload=PAYLOAD, idempotency_key="k-1")
    assert log.status == NotificationStatus.SKIPPED
    assert log.channel == NotificationChannel.EMAIL
    assert "STAFF_NOTIFICATION_EMAILS" in log.error_message
    assert mail.outbox == []


@pytest.mark.django_db
def test_письмо_уходит_всем_получателям_и_фиксируется_снимок(получатели):
    log = notify_staff(event="staff_order_created", payload=PAYLOAD, idempotency_key="k-2")
    log.refresh_from_db()
    assert log.status == NotificationStatus.SENT
    assert log.subject == "Новый заказ №П-1 — 1000.00 RUB"
    assert log.recipients == "m1@example.com, m2@example.com"
    assert len(mail.outbox) == 1
    письмо = mail.outbox[0]
    assert письмо.to == ["m1@example.com", "m2@example.com"]
    assert письмо.from_email == "site@example.com"
    assert "П-1" in письмо.body and PAYLOAD["admin_url"] in письмо.body


@pytest.mark.django_db
def test_повтор_ключа_не_создаёт_второй_строки_и_письма(получатели):
    first = notify_staff(event="staff_order_created", payload=PAYLOAD, idempotency_key="k-3")
    second = notify_staff(event="staff_order_created", payload=PAYLOAD, idempotency_key="k-3")
    assert first.pk == second.pk
    assert NotificationLog.objects.filter(idempotency_key="k-3").count() == 1
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_повтор_из_админки_идёт_по_снимку_получателей(получатели, settings):
    log = notify_staff(event="staff_order_created", payload=PAYLOAD, idempotency_key="k-4")
    NotificationLog.objects.filter(pk=log.pk).update(status=NotificationStatus.FAILED)
    settings.STAFF_NOTIFICATION_EMAILS = ["new@example.com"]  # список поменяли после постановки
    mail.outbox.clear()

    send_notification_task(log.pk)
    assert mail.outbox[0].to == ["m1@example.com", "m2@example.com"]


# ═══════════ классификация ошибок канала ═══════════


@pytest.mark.parametrize(
    "исключение,ожидаемый_класс",
    [
        (smtplib.SMTPAuthenticationError(535, b"bad creds"), PermanentChannelError),
        (smtplib.SMTPRecipientsRefused({"x@y": (550, b"no")}), PermanentChannelError),
        (smtplib.SMTPSenderRefused(553, b"no", "a@b"), PermanentChannelError),
        (smtplib.SMTPResponseException(451, b"try later"), RetryableChannelError),
        (smtplib.SMTPServerDisconnected("gone"), RetryableChannelError),
        (ConnectionRefusedError(), RetryableChannelError),
        (TimeoutError(), RetryableChannelError),
    ],
)
def test_smtp_ошибки_классифицируются(settings, исключение, ожидаемый_класс):
    settings.EMAIL_HOST = "smtp.example.com"
    with mock.patch("django.core.mail.EmailMessage.send", side_effect=исключение):
        with pytest.raises(ожидаемый_класс) as info:
            email_channel.send_email("t", "b", ["m@example.com"])
    # В описании ошибки нет адресов — только класс и код.
    assert "example.com" not in str(info.value)


def test_без_smtp_хоста_канал_отказывает_permanent(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = ""
    with pytest.raises(PermanentChannelError, match="EMAIL_HOST"):
        email_channel.send_email("t", "b", ["m@example.com"])


@pytest.fixture
def email_log(db):
    return NotificationLog.objects.create(
        channel=NotificationChannel.EMAIL,
        event="staff_order_created",
        status=NotificationStatus.QUEUED,
        subject="t",
        text="b",
        recipients="m@example.com",
    )


@pytest.mark.django_db
def test_задача_permanent_не_ретраит(email_log):
    with mock.patch(
        "apps.notifications.channels.email.send_email",
        side_effect=PermanentChannelError("SMTPRecipientsRefused"),
    ) as sender:
        with mock.patch.object(send_notification_task, "retry") as retry:
            send_notification_task(email_log.pk)
    sender.assert_called_once()
    retry.assert_not_called()
    email_log.refresh_from_db()
    assert email_log.status == NotificationStatus.FAILED
    assert email_log.error_kind == NotificationErrorKind.PERMANENT


@pytest.mark.django_db
def test_задача_retryable_ретраит_с_backoff(email_log):
    with mock.patch(
        "apps.notifications.channels.email.send_email",
        side_effect=RetryableChannelError("SMTPServerDisconnected"),
    ):
        with mock.patch.object(
            send_notification_task, "retry", side_effect=Exception("stop-here")
        ) as retry:
            with pytest.raises(Exception, match="stop-here"):
                send_notification_task(email_log.pk)
    assert retry.call_args.kwargs["countdown"] >= 30
    email_log.refresh_from_db()
    assert email_log.status == NotificationStatus.FAILED
    assert email_log.error_kind == NotificationErrorKind.RETRYABLE


# ═══════════ команда проверки транспорта ═══════════


def test_команда_шлёт_контрольное_письмо_на_явный_адрес(settings):
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    out = StringIO()
    call_command("notifications_email_check", to="check@example.com", stdout=out)
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["check@example.com"]
    assert "Письмо отправлено" in out.getvalue()


def test_команда_без_транспорта_падает_понятно(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = ""
    with pytest.raises(CommandError, match="EMAIL_HOST"):
        call_command("notifications_email_check", to="check@example.com", stdout=StringIO())
