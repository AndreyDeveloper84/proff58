"""Модели уведомлений: transactional outbox отправки (#431, M-08)."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class NotificationChannel(models.TextChoices):
    MAX = "max", _("MAX мессенджер")
    EMAIL = "email", _("E-mail")


class NotificationStatus(models.TextChoices):
    # #431 (M-08): состояния outbox. queued → sending → sent | failed;
    # unknown — отправлено, но подтверждение потеряно (crash-after-send).
    QUEUED = "queued", _("В очереди")
    SENDING = "sending", _("Отправляется")
    SENT = "sent", _("Отправлено")
    FAILED = "failed", _("Ошибка")
    SKIPPED = "skipped", _("Пропущено")
    UNKNOWN = "unknown", _("Статус неизвестен")


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
        db_index=True,
    )
    error_message = models.TextField(_("Ошибка"), blank=True)
    idempotency_key = models.CharField(
        _("Ключ идемпотентности"),
        max_length=255,
        blank=True,
        db_index=True,
    )
    # #431 (M-08): полезная нагрузка задачи хранится в строке outbox, чтобы задача
    # работала по log_id (claim), а не переносила все поля через очередь.
    chat_id = models.BigIntegerField(_("MAX chat ID"), null=True, blank=True)
    text = models.TextField(_("Текст сообщения"), blank=True)
    provider_message_id = models.CharField(
        _("ID сообщения у провайдера"), max_length=128, blank=True
    )

    class Meta:
        verbose_name = _("Лог уведомления")
        verbose_name_plural = _("Лог уведомлений")
        ordering = ["-created_at"]
        constraints = [
            # #431 (M-08): дедуп на уровне БД — не более одной строки на непустой
            # idempotency_key. Гарантирует идемпотентность при конкуренции процессов.
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_notification_idempotency_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.event} → {self.channel} [{self.status}]"
