"""Модели доставки: зоны, способы, пункты самовывоза.

Зональная доставка по Пензе и области. Зоны и тарифы хранятся в БД —
администратор настраивает их без правки кода. Самовывоз — отдельный способ
с нулевой стоимостью.

Дефолтные зоны создаются data-миграцией:
- «Пенза город» — 300 ₽, бесплатно от 5 000 ₽
- «Пензенская область» — 500 ₽, бесплатно от 10 000 ₽
- «Самовывоз» — 0 ₽
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class DeliveryType(models.TextChoices):
    """Способы доставки."""

    COURIER = "courier", _("Курьерская доставка")
    PICKUP = "pickup", _("Самовывоз")


class DeliveryZone(TimeStampedModel):
    """Зона доставки с тарифом.

    Каждая зона определяет стоимость доставки и порог бесплатной доставки.
    Администратор может деактивировать зону без удаления.
    """

    name = models.CharField(_("Название зоны"), max_length=200)
    slug = models.SlugField(_("Слаг"), max_length=100, unique=True)
    delivery_type = models.CharField(
        _("Способ доставки"),
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.COURIER,
    )
    price = models.DecimalField(
        _("Стоимость доставки"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    free_from = models.DecimalField(
        _("Бесплатно от суммы"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Сумма заказа, начиная с которой доставка бесплатна. Пусто = нет порога."),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # #429 (M-05, ADR #444): внешняя зона (СДЭК) — стоимость всегда через API
    # перевозчика (integration_ship), порог бесплатной доставки НЕ применяется.
    # Авторасчёт возможен только при заполненных весе/габаритах у всех товаров;
    # иначе — ручной расчёт менеджером (manual_required).
    is_external = models.BooleanField(
        _("Внешний перевозчик (СДЭК)"),
        default=False,
        help_text=_("Стоимость по API перевозчика; порог бесплатной доставки не применяется."),
    )
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_active = models.BooleanField(_("Активна"), default=True)

    class Meta:
        verbose_name = _("Зона доставки")
        verbose_name_plural = _("Зоны доставки")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class PickupPoint(TimeStampedModel):
    """Пункт самовывоза.

    Адрес, часы работы. Администратор может деактивировать пункт.
    """

    name = models.CharField(_("Название"), max_length=200)
    address = models.CharField(_("Адрес"), max_length=500)
    working_hours = models.CharField(
        _("Часы работы"),
        max_length=200,
        help_text=_("Например: Пн-Пт 9:00-18:00, Сб 10:00-15:00"),
    )
    is_active = models.BooleanField(_("Активен"), default=True)

    class Meta:
        verbose_name = _("Пункт самовывоза")
        verbose_name_plural = _("Пункты самовывоза")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.address})"
