"""Модели оплаты — Payment и связь с заказом (#8)."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class PaymentMethod(models.TextChoices):
    YOOKASSA = "yookassa", _("ЮKassa (карта/СБП)")
    INVOICE = "invoice", _("Счёт (B2B)")
    CASH = "cash", _("При получении")


class PaymentStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает оплаты")
    WAITING_CAPTURE = "waiting_for_capture", _("Ожидает подтверждения")
    SUCCEEDED = "succeeded", _("Оплачен")
    CANCELED = "canceled", _("Отменён")
    REFUNDED = "refunded", _("Возвращён")


class Payment(TimeStampedModel):
    """Платёж — привязан к заказу, хранит данные ЮKassa."""

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("Заказ"),
    )
    yookassa_id = models.CharField(
        _("ID платежа ЮKassa"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
    )
    method = models.CharField(
        _("Способ оплаты"),
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.YOOKASSA,
    )
    status = models.CharField(
        _("Статус"),
        max_length=24,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    amount = models.DecimalField(_("Сумма"), max_digits=14, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    confirmation_url = models.URLField(_("URL оплаты"), blank=True)
    idempotency_key = models.CharField(
        _("Ключ идемпотентности"),
        max_length=64,
        unique=True,
    )
    webhook_payload = models.JSONField(
        _("Последний webhook payload"),
        default=dict,
        blank=True,
    )
    paid_at = models.DateTimeField(_("Дата оплаты"), null=True, blank=True)

    class Meta:
        verbose_name = _("Платёж")
        verbose_name_plural = _("Платежи")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Платёж {self.yookassa_id or self.pk} [{self.status}]"
