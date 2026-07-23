"""Модели доставки: зоны, способы, пункты самовывоза.

Зональная доставка по Пензе и области. Зоны и тарифы хранятся в БД —
администратор настраивает их без правки кода. Самовывоз — отдельный способ
с нулевой стоимостью.

Дефолтные зоны создаются data-миграциями; актуальные значения после
``0004_adr444_zones`` (контракт ADR-0013):
- «Пенза (курьер)» — 500 ₽, бесплатно от 7 000 ₽
- «Пензенская область (СДЭК)» — ``is_external``: стоимость по API перевозчика,
  порог бесплатной доставки не применяется
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


class DeliverySlot(TimeStampedModel):
    """Слот доставки: дата + временной интервал с ограниченной вместимостью (#569).

    Менеджер создаёт слоты в админке; checkout отдаёт покупателю только
    активные будущие слоты со свободными местами. Занятость НЕ хранится
    счётчиком — считается по «живым» заказам слота (fulfillment != cancelled,
    см. apps.orders.slots.occupied_counts): отмена заказа автоматически
    освобождает место, дрейф счётчика невозможен. Единственный автоматический
    освободитель места — отмена заказа (менеджером/1С); истечение 30-минутного
    резерва товара (#568) слот не освобождает.
    """

    date = models.DateField(_("Дата"), db_index=True)
    starts_at = models.TimeField(_("Начало интервала"))
    ends_at = models.TimeField(_("Конец интервала"))
    delivery_method = models.CharField(
        _("Способ доставки"),
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.COURIER,
    )
    # null = слот действует для всех зон. PROTECT: зону со слотами нельзя
    # удалить (деактивировать — можно); превращение зонального слота в
    # глобальный через SET_NULL было бы молчаливым расширением географии.
    zone = models.ForeignKey(
        DeliveryZone,
        verbose_name=_("Зона доставки"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="slots",
        help_text=_("Пусто — слот доступен во всех зонах."),
    )
    capacity = models.PositiveSmallIntegerField(
        _("Лимит заказов"),
        default=4,
        validators=[MinValueValidator(1)],
    )
    is_active = models.BooleanField(_("Активен"), default=True)

    class Meta:
        verbose_name = _("Слот доставки")
        verbose_name_plural = _("Слоты доставки")
        ordering = ["date", "starts_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "starts_at", "ends_at", "delivery_method", "zone"],
                name="uniq_delivery_slot_window",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                check=models.Q(ends_at__gt=models.F("starts_at")),
                name="delivery_slot_ends_after_starts",
            ),
        ]
        indexes = [models.Index(fields=["is_active", "date"], name="slot_active_date_idx")]

    def __str__(self) -> str:
        window = f"{self.starts_at:%H:%M}–{self.ends_at:%H:%M}"
        scope = self.zone.name if self.zone_id else "все зоны"
        return f"{self.date} {window} ({scope})"


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
