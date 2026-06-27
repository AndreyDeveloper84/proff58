"""Заявки с карточки товара (лиды): запрос цены и уведомление о поступлении."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class InquiryKind(models.TextChoices):
    PRICE_REQUEST = "price_request", _("Запрос цены")
    RESTOCK_NOTIFY = "restock_notify", _("Уведомить о поступлении")
    CONSULTATION = "consultation", _("Консультация")


class InquiryStatus(models.TextChoices):
    NEW = "new", _("Новая")
    PROCESSED = "processed", _("Обработана")


class ProductInquiry(TimeStampedModel):
    """Заявка покупателя по конкретному товару (lead capture с PDP)."""

    kind = models.CharField(_("Тип"), max_length=20, choices=InquiryKind.choices)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="inquiries",
        verbose_name=_("Товар"),
        null=True,
        blank=True,
    )
    phone = models.CharField(_("Телефон"), max_length=20)
    name = models.CharField(_("Имя"), max_length=120, blank=True)
    message = models.TextField(_("Сообщение"), blank=True)
    status = models.CharField(
        _("Статус"), max_length=12, choices=InquiryStatus.choices, default=InquiryStatus.NEW
    )

    class Meta:
        verbose_name = _("Заявка по товару")
        verbose_name_plural = _("Заявки по товарам")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "kind"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.phone} ({self.product_id or '—'})"
