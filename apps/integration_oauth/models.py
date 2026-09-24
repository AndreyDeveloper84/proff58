"""Привязка пользователя сайта к внешнему аккаунту VK ID / Яндекс ID.

Токены провайдеров НЕ храним: они нужны ровно на время колбэка (обмен кода →
профиль), дальше сайт живёт своей Django-сессией. В записи — только
идентификатор у провайдера и снимок того, что он отдал (почта, имя) для показа в
кабинете и админке.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class OAuthAccount(models.Model):
    """Внешний аккаунт, через который пользователь входит на сайт.

    Инварианты на уровне схемы:
    - один аккаунт провайдера — ровно один пользователь сайта
      (``provider`` + ``provider_user_id``);
    - у пользователя не больше одной привязки каждого провайдера
      (``user`` + ``provider``).
    """

    class Provider(models.TextChoices):
        VKID = "vkid", _("VK ID")
        YANDEX = "yandex", _("Яндекс ID")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="oauth_accounts",
        verbose_name=_("Пользователь"),
    )
    provider = models.CharField(_("Провайдер"), max_length=16, choices=Provider.choices)
    provider_user_id = models.CharField(_("ID у провайдера"), max_length=64)
    email = models.EmailField(_("E-mail от провайдера"), blank=True)
    full_name = models.CharField(_("Имя от провайдера"), max_length=255, blank=True)
    linked_at = models.DateTimeField(_("Привязан"), auto_now_add=True)
    last_login_at = models.DateTimeField(_("Последний вход"), null=True, blank=True)

    class Meta:
        verbose_name = _("Привязка VK ID / Яндекс ID")
        verbose_name_plural = _("Привязки VK ID / Яндекс ID")
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                name="integration_oauth_unique_provider_account",
            ),
            models.UniqueConstraint(
                fields=["user", "provider"],
                name="integration_oauth_unique_user_provider",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} {self.provider_user_id} → {self.user_id}"
