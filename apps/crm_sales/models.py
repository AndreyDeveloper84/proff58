"""CRM · Продажи — сделки и воронка."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class DealStage(models.TextChoices):
    NEW = "new", _("Новая")
    IN_PROGRESS = "in_progress", _("В работе")
    WON = "won", _("Выиграна")
    LOST = "lost", _("Проиграна")


class Deal(TimeStampedModel):
    """Сделка CRM — создаётся из заказа или вручную."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_deals",
    )
    title = models.CharField(_("Название"), max_length=255)
    stage = models.CharField(
        _("Этап"),
        max_length=20,
        choices=DealStage.choices,
        default=DealStage.NEW,
    )
    amount = models.DecimalField(
        _("Сумма"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    order_id = models.PositiveIntegerField(_("ID заказа"), null=True, blank=True)
    notes = models.TextField(_("Заметки"), blank=True)

    class Meta:
        verbose_name = _("Сделка")
        verbose_name_plural = _("Сделки")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
