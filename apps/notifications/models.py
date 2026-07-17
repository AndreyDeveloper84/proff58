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


class NotificationCategory(models.TextChoices):
    """Категории для preference-тумблеров и фильтрации истории (#515).

    ACCOUNT — сервисные сообщения (напр. `max_connected`): не имеют отдельного
    тумблера, гасятся только мастер-переключателем канала (`max_enabled`).
    """

    ACCOUNT = "account", _("Аккаунт")
    ORDER_UPDATES = "order_updates", _("Статусы заказов")
    PRODUCT_AVAILABILITY = "product_availability", _("Появление товара")
    MARKETING = "marketing", _("Маркетинг")


class UserNotificationPreference(TimeStampedModel):
    """Пользовательские настройки уведомлений (#515).

    `marketing_enabled` — default False (явный opt-in, §consent); сервисные
    категории (`order_updates`, `product_availability`) независимы от него и
    включены по умолчанию. `max_enabled` — мастер-переключатель канала MAX:
    выключен → уведомления не уходят вообще, независимо от категорий.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
        verbose_name=_("Пользователь"),
    )
    max_enabled = models.BooleanField(_("Канал MAX включён"), default=True)
    order_updates_enabled = models.BooleanField(_("Статусы заказов"), default=True)
    product_availability_enabled = models.BooleanField(_("Появление товара"), default=True)
    marketing_enabled = models.BooleanField(_("Маркетинговые рассылки"), default=False)
    marketing_consent_at = models.DateTimeField(_("Согласие на маркетинг"), null=True, blank=True)
    marketing_consent_version = models.CharField(_("Версия согласия"), max_length=32, blank=True)

    class Meta:
        verbose_name = _("Настройки уведомлений")
        verbose_name_plural = _("Настройки уведомлений")

    def __str__(self) -> str:
        return f"Настройки уведомлений {self.user_id}"


class Notification(TimeStampedModel):
    """User-facing intent/история уведомлений (#515).

    В отличие от `NotificationLog` (техническая outbox-строка одной попытки
    доставки одним каналом) — это то, что видит пользователь в центре
    уведомлений: один intent может не иметь доставки вовсе (категория выключена
    в preferences — `policy_skip_reason` объясняет почему, без внешней отправки).
    `title`/`body`/`data` — снимок на момент создания (шаблон версионирован в
    коде, `template_version`), не пересчитываются при изменении шаблона.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("Пользователь"),
    )
    event = models.CharField(_("Событие"), max_length=100, db_index=True)
    category = models.CharField(
        _("Категория"), max_length=32, choices=NotificationCategory.choices, db_index=True
    )
    title = models.CharField(_("Заголовок"), max_length=255)
    body = models.TextField(_("Текст"), blank=True)
    data = models.JSONField(_("Данные"), default=dict, blank=True)
    template_version = models.PositiveIntegerField(_("Версия шаблона"), default=1)
    idempotency_key = models.CharField(
        _("Ключ идемпотентности"), max_length=255, blank=True, db_index=True
    )
    # #514/#431: связь с существующим outbox — nullable, т.к. при выключенной
    # категории доставка вообще не создаётся (см. policy_skip_reason).
    delivery = models.ForeignKey(
        NotificationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification",
        verbose_name=_("Доставка"),
    )
    policy_skip_reason = models.CharField(
        _("Причина пропуска по preferences"), max_length=64, blank=True
    )
    read_at = models.DateTimeField(_("Прочитано"), null=True, blank=True)

    class Meta:
        verbose_name = _("Уведомление")
        verbose_name_plural = _("Уведомления")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_notification_intent_idempotency_key",
            )
        ]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self) -> str:
        return f"{self.event} → user={self.user_id} [{'прочитано' if self.read_at else 'новое'}]"
