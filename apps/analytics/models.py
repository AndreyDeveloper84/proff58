"""Модель хранения событий аналитики витрины и checkout."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class EventType(models.TextChoices):
    SEARCH = "search", _("Поиск")
    PRODUCT_VIEW = "product_view", _("Просмотр товара")
    ADD_TO_CART = "add_to_cart", _("Добавление в корзину")
    CHECKOUT_START = "checkout_start", _("Начало оформления")
    ORDER_CREATED = "order_created", _("Заказ создан")
    PAYMENT_STARTED = "payment_started", _("Оплата начата")
    PAYMENT_SUCCESS = "payment_success", _("Оплата успешна")
    PAYMENT_FAIL = "payment_fail", _("Оплата не удалась")


class AnalyticsEvent(TimeStampedModel):
    """Запись аналитического события витрины/checkout.

    Персональные и платёжные данные не сохраняются — фильтруются в ``services.track()``.
    """

    event_type = models.CharField(
        _("Тип события"),
        max_length=30,
        choices=EventType.choices,
    )
    session_id = models.CharField(_("ID сессии"), max_length=255, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Пользователь"),
        related_name="analytics_events",
    )
    payload = models.JSONField(_("Данные события"), default=dict, blank=True)

    class Meta:
        verbose_name = _("Событие аналитики")
        verbose_name_plural = _("События аналитики")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} ({self.created_at})"
