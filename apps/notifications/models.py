"""Модели уведомлений: лог отправки для аудита."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class NotificationChannel(models.TextChoices):
    MAX = "max", _("MAX мессенджер")
    EMAIL = "email", _("E-mail")


class NotificationStatus(models.TextChoices):
    SENT = "sent", _("Отправлено")
    FAILED = "failed", _("Ошибка")
    SKIPPED = "skipped", _("Пропущено")


class NotificationLog(TimeStampedModel):
    """Журнал отправленных уведомлений."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs",
    )
    channel = models.CharField(
        _("Канал"),
        max_length=10,
        choices=NotificationChannel.choices,
    )
    event = models.CharField(_("Событие"), max_length=100, db_index=True)
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=NotificationStatus.choices,
    )
    error_message = models.TextField(_("Ошибка"), blank=True)
    idempotency_key = models.CharField(
        _("Ключ идемпотентности"),
        max_length=255,
        blank=True,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Лог уведомления")
        verbose_name_plural = _("Лог уведомлений")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event} → {self.channel} [{self.status}]"
