"""Подписчики событий заявок. Сбой канала уведомления не валит создание заявки."""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.leads")


def _staff_payload(inquiry_id: int) -> dict | None:
    from django.utils import timezone

    from apps.notifications.services import admin_url

    from .models import ProductInquiry

    inquiry = ProductInquiry.objects.select_related("product").filter(pk=inquiry_id).first()
    if inquiry is None:
        return None
    product = "—"
    if inquiry.product is not None:
        product = inquiry.product.name
        if inquiry.product.article:
            product = f"{product} (арт. {inquiry.product.article})"
    return {
        "inquiry_id": inquiry.pk,
        "kind": inquiry.get_kind_display(),
        "created_at": timezone.localtime(inquiry.created_at).strftime("%d.%m.%Y %H:%M"),
        "product": product,
        "name": inquiry.name or "—",
        "phone": inquiry.phone,
        "message": inquiry.message or "—",
        "admin_url": admin_url(f"/admin/leads/productinquiry/{inquiry.pk}/change/"),
    }


def notify_new_inquiry(sender, inquiry_id, kind, product_id, **kwargs):
    """Реакция на product_inquiry_created: уведомить менеджеров.

    Письмо сотрудникам через outbox уведомлений (DRF-2296) плюс запись в лог.
    Исключения глушим: заявка уже сохранена, потеря уведомления не должна
    ломать ответ API.
    """
    try:
        logger.info("Новая заявка #%s (%s) по товару %s", inquiry_id, kind, product_id)
        payload = _staff_payload(inquiry_id)
        if payload is None:
            return
        from apps.notifications.services import notify_staff

        notify_staff(
            event="staff_inquiry_created",
            payload=payload,
            idempotency_key=f"staff-inquiry-{inquiry_id}",
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой обработки product_inquiry_created")
