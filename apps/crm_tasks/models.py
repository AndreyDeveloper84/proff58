"""CRM · Задачи — задачи и тикеты менеджеров."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class TaskStatus(models.TextChoices):
    OPEN = "open", _("Открыта")
    IN_PROGRESS = "in_progress", _("В работе")
    DONE = "done", _("Выполнена")
    CANCELLED = "cancelled", _("Отменена")


class Task(TimeStampedModel):
    """Задача менеджера — привязана к клиенту или заказу."""

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_tasks",
    )
    title = models.CharField(_("Название"), max_length=255)
    description = models.TextField(_("Описание"), blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.OPEN,
    )
    due_date = models.DateTimeField(_("Срок"), null=True, blank=True)
    order_id = models.PositiveIntegerField(_("ID заказа"), null=True, blank=True)

    class Meta:
        verbose_name = _("Задача")
        verbose_name_plural = _("Задачи")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
