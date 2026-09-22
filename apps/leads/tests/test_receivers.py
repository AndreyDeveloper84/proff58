"""Уведомление сотрудников о новой заявке (DRF-2296): письмо на каждый тип заявки,
дедуп, сбой канала не ломает создание заявки."""

from __future__ import annotations

import logging
from unittest import mock

import pytest
from django.core import mail

from apps.leads.models import InquiryKind
from apps.leads.receivers import notify_new_inquiry
from apps.leads.services import create_inquiry
from apps.notifications.models import NotificationLog, NotificationStatus


@pytest.fixture(autouse=True)
def _почта(settings):
    settings.STAFF_NOTIFICATION_EMAILS = ["manager@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    settings.SITE_URL = "https://proff58.ru"


@pytest.mark.django_db
def test_notify_logs_inquiry(product, caplog):
    with caplog.at_level(logging.INFO, logger="apps.leads"):
        notify_new_inquiry(sender=None, inquiry_id=1, kind="price_request", product_id=product.pk)
    assert any("price_request" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
@pytest.mark.parametrize("kind", [k.value for k in InquiryKind])
def test_каждый_тип_заявки_даёт_письмо(product, kind, django_capture_on_commit_callbacks):
    товар = None if kind == InquiryKind.CONSULTATION else product
    with django_capture_on_commit_callbacks(execute=True):
        inquiry = create_inquiry(
            kind=kind, product=товар, phone="+79001112233", name="Пётр", message="Позвоните"
        )
    assert len(mail.outbox) == 1
    письмо = mail.outbox[0]
    assert str(InquiryKind(kind).label) in письмо.subject
    assert "+79001112233" in письмо.body and "Пётр" in письмо.body
    assert f"https://proff58.ru/admin/leads/productinquiry/{inquiry.pk}/change/" in письмо.body
    if товар is not None:
        assert "Дрель" in письмо.body and "ART-LEAD-1" in письмо.body


@pytest.mark.django_db
def test_повтор_события_не_дублирует_письмо(product, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        inquiry = create_inquiry(
            kind=InquiryKind.PRICE_REQUEST, product=product, phone="+79001112233"
        )
    notify_new_inquiry(sender=None, inquiry_id=inquiry.pk, kind=inquiry.kind, product_id=product.pk)
    assert len(mail.outbox) == 1
    assert (
        NotificationLog.objects.filter(idempotency_key=f"staff-inquiry-{inquiry.pk}").count() == 1
    )


@pytest.mark.django_db
def test_сбой_постановки_не_ломает_заявку(product, django_capture_on_commit_callbacks):
    with mock.patch(
        "apps.notifications.tasks.send_notification_task.delay",
        side_effect=ConnectionError("redis down"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            inquiry = create_inquiry(
                kind=InquiryKind.PRICE_REQUEST, product=product, phone="+79001112233"
            )
    assert inquiry.pk is not None
    log = NotificationLog.objects.get(idempotency_key=f"staff-inquiry-{inquiry.pk}")
    assert (
        log.status == NotificationStatus.FAILED
    )  # DRF-2293: очередь недоступна → повтор из админки
