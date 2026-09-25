"""CRM · Клиенты — профиль клиента и история взаимодействий."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class InteractionType(models.TextChoices):
    REGISTRATION = "registration", _("Регистрация")
    ORDER = "order", _("Заказ")
    CALL = "call", _("Звонок")
    MESSAGE = "message", _("Сообщение")
    NOTE = "note", _("Заметка")


class ClientProfile(TimeStampedModel):
    """Расширенный профиль клиента для CRM."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="crm_profile",
    )
    source = models.CharField(_("Источник"), max_length=100, blank=True)
    tags = models.JSONField(_("Теги"), default=list, blank=True)
    notes = models.TextField(_("Заметки"), blank=True)

    class Meta:
        verbose_name = _("Профиль клиента")
        verbose_name_plural = _("Профили клиентов")

    def __str__(self) -> str:
        return f"CRM: {self.user}"


class Interaction(TimeStampedModel):
    """Запись о взаимодействии с клиентом."""

    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name="interactions",
    )
    interaction_type = models.CharField(
        _("Тип"),
        max_length=20,
        choices=InteractionType.choices,
    )
    summary = models.CharField(_("Описание"), max_length=500)
    metadata = models.JSONField(_("Метаданные"), default=dict, blank=True)

    class Meta:
        verbose_name = _("Взаимодействие")
        verbose_name_plural = _("Взаимодействия")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_interaction_type_display()}: {self.summary[:50]}"
