"""Сервисный слой заявок: единая точка создания + эмит доменного события."""

from __future__ import annotations

from django.db import transaction

from apps.core.events import product_inquiry_created

from .models import ProductInquiry


def create_inquiry(*, kind, product, phone, name="", message=""):
    """Создать заявку по товару и опубликовать факт `product_inquiry_created`.

    Событие эмитится через on_commit — подписчик видит уже закоммиченную запись.
    """
    inquiry = ProductInquiry.objects.create(
        kind=kind, product=product, phone=phone, name=name, message=message
    )

    def _emit():
        product_inquiry_created.send(
            sender=ProductInquiry,
            inquiry_id=inquiry.pk,
            kind=inquiry.kind,
            product_id=inquiry.product_id,
        )

    transaction.on_commit(_emit)
    return inquiry
