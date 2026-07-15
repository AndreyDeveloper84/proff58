"""Модели интеграции MAX: привязка аккаунта и одноразовая попытка авторизации (#492).

Архитектура входа через MAX — «одноразовая попытка» (deeplink + QR + polling):
сайт создаёт MaxAuthAttempt, отдаёт диплинк с одноразовым идентификатором; бот по
диплинку и переданному контакту завершает попытку; сайт опрашивает статус и по
`completed` поднимает Django-сессию. Телефон — основной идентификатор; MAX —
дополнительный способ входа (см. постановку в issue #492).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MaxAccount(models.Model):
    """Привязка пользователя сайта к аккаунту MAX.

    Инварианты (§9.1): один `max_user_id` — ровно один пользователь (unique);
    у пользователя — одна привязка (OneToOne). `username` MAX не используется как
    идентификатор — только для отображения.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="max_account",
        verbose_name=_("Пользователь"),
    )
    max_user_id = models.BigIntegerField(_("MAX user_id"), unique=True)
    # chat_id диалога с ботом — для отправки сервисных сообщений (может обновляться).
    chat_id = models.BigIntegerField(_("MAX chat_id"), null=True, blank=True)
    phone = models.CharField(_("Телефон (норм.)"), max_length=20)
    first_name = models.CharField(_("Имя"), max_length=150, blank=True)
    last_name = models.CharField(_("Фамилия"), max_length=150, blank=True)
    username = models.CharField(_("MAX username"), max_length=150, blank=True)
    phone_verified_at = models.DateTimeField(_("Телефон подтверждён"), null=True, blank=True)
    linked_at = models.DateTimeField(_("Привязан"), auto_now_add=True)
    last_login_at = models.DateTimeField(_("Последний вход"), null=True, blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)

    class Meta:
        verbose_name = _("Привязка MAX")
        verbose_name_plural = _("Привязки MAX")

    def __str__(self) -> str:
        return f"MAX {self.max_user_id} → {self.user_id}"


class MaxAuthAttempt(models.Model):
    """Одноразовая попытка авторизации через MAX (§9.2).

    Живёт TTL минут (MAX_AUTH_ATTEMPT_TTL, дефолт 5). Диплинк несёт только
    случайные public_id + secret (без PII, §11.1). Завершение идемпотентно (§11.4),
    привязано к браузер-сессии, создавшей попытку (§11.2).
    """

    class Operation(models.TextChoices):
        LOGIN = "login", _("Вход/регистрация")
        REGISTRATION = "registration", _("Регистрация")
        LINK = "link", _("Привязка MAX")
        CONFIRM_LOGIN = "confirm_login", _("Подтверждение входа")

    class Status(models.TextChoices):
        PENDING = "pending", _("Ожидание")
        CONFIRMATION_REQUIRED = "confirmation_required", _("Требует подтверждения")
        COMPLETED = "completed", _("Завершена")
        CANCELLED = "cancelled", _("Отменена")
        EXPIRED = "expired", _("Истекла")
        FAILED = "failed", _("Ошибка")

    # public_id — в диплинке/URL статуса; secret_hash — проверка подлинности старта из бота.
    public_id = models.UUIDField(_("Публичный id"), default=uuid.uuid4, unique=True, editable=False)
    secret_hash = models.CharField(_("Хэш секрета"), max_length=64)
    # Привязка к браузеру, создавшему попытку (§11.2): завершать вход только в нём.
    browser_session_key = models.CharField(_("Ключ браузер-сессии"), max_length=64)
    operation_type = models.CharField(
        _("Тип операции"), max_length=20, choices=Operation.choices, default=Operation.LOGIN
    )
    # Для link/confirm_login пользователь известен заранее (создавший попытку).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="max_auth_attempts",
        verbose_name=_("Пользователь"),
    )
    max_user_id = models.BigIntegerField(_("MAX user_id"), null=True, blank=True)
    chat_id = models.BigIntegerField(_("MAX chat_id"), null=True, blank=True)
    status = models.CharField(
        _("Статус"), max_length=24, choices=Status.choices, default=Status.PENDING
    )
    failure_reason = models.CharField(_("Причина ошибки"), max_length=64, blank=True)
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    expires_at = models.DateTimeField(_("Истекает"))
    completed_at = models.DateTimeField(_("Завершена в"), null=True, blank=True)

    class Meta:
        verbose_name = _("Попытка авторизации MAX")
        verbose_name_plural = _("Попытки авторизации MAX")
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.operation_type}:{self.public_id} [{self.status}]"

    @staticmethod
    def default_ttl() -> timedelta:
        return timedelta(minutes=getattr(settings, "MAX_AUTH_ATTEMPT_TTL_MINUTES", 5))

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            self.Status.COMPLETED,
            self.Status.CANCELLED,
            self.Status.EXPIRED,
            self.Status.FAILED,
        }
