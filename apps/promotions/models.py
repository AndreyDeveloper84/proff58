"""Акции и промокоды (#571).

Одна модель `Promotion` покрывает все три типа промо MVP: автоакция на товар,
автоакция на категорию, промокод (акция с непустым ``promo_code`` — применяется
только после ввода кода покупателем). Скидки считает ТОЛЬКО сервер
(`apps.promotions.services.compute_promotions`); модуль включается бизнес-флагом
``promotions`` (SiteSettings, default off).

Границы (CLAUDE.md §4): promotions — Слой 1 (Магазин), зависит от core/catalog;
orders вызывает promotions через сервисный слой (как pricing/delivery).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class DiscountType(models.TextChoices):
    PERCENT = "percent", _("Процент")
    FIXED = "fixed_amount", _("Фиксированная сумма")
    FREE_DELIVERY = "free_delivery", _("Бесплатная доставка")


class PromoScope(models.TextChoices):
    PRODUCT = "product", _("Товары")
    CATEGORY = "category", _("Категории")
    CART = "cart", _("Корзина")


class Promotion(TimeStampedModel):
    """Акция/промокод.

    Автоакция (``promo_code`` пуст) применяется сама; акция с кодом — только
    после ввода кода (один код на корзину). ``free_delivery`` — всегда кодовая
    награда со scope=cart (автоматическая бесплатная доставка уже существует
    в delivery через ``DeliveryZone.free_from`` — не дублируем).
    """

    name = models.CharField(_("Название"), max_length=255)
    is_active = models.BooleanField(_("Активна"), default=True, db_index=True)
    starts_at = models.DateTimeField(_("Начало"), null=True, blank=True)
    ends_at = models.DateTimeField(_("Окончание"), null=True, blank=True)
    discount_type = models.CharField(_("Тип выгоды"), max_length=16, choices=DiscountType.choices)
    discount_value = models.DecimalField(
        _("Размер"),
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text=_("Процент (1–100) или сумма в валюте корзины; для бесплатной доставки — 0."),
    )
    scope = models.CharField(_("Область"), max_length=10, choices=PromoScope.choices)
    products = models.ManyToManyField(
        "catalog.Product", blank=True, related_name="promotions", verbose_name=_("Товары")
    )
    categories = models.ManyToManyField(
        "catalog.Category",
        blank=True,
        related_name="promotions",
        verbose_name=_("Категории"),
        help_text=_("Действует на всё поддерево выбранных категорий."),
    )
    promo_code = models.CharField(
        _("Промокод"),
        max_length=40,
        blank=True,
        default="",
        help_text=_("Пусто — акция автоматическая; иначе применяется только по коду."),
    )
    priority = models.IntegerField(
        _("Приоритет"),
        default=0,
        help_text=_("Тай-брейк при равной выгоде на строку: больше — важнее."),
    )

    class Meta:
        # См. content.Promotion — там страница про акцию. Здесь настоящая скидка.
        verbose_name = _("Скидка / промокод")
        verbose_name_plural = _("Скидки и промокоды")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("promo_code"),
                condition=~Q(promo_code=""),
                name="uniq_promotion_code_ci",
            ),
        ]

    def __str__(self) -> str:
        code = f" [{self.promo_code}]" if self.promo_code else ""
        return f"{self.name}{code}"

    def clean(self):
        errors: dict[str, str] = {}
        if self.discount_type == DiscountType.PERCENT and not (0 < self.discount_value <= 100):
            errors["discount_value"] = "Процент должен быть в диапазоне 1–100."
        if self.discount_type == DiscountType.FIXED and self.discount_value <= 0:
            errors["discount_value"] = "Фиксированная скидка должна быть больше нуля."
        if self.discount_type == DiscountType.FREE_DELIVERY:
            if not self.promo_code:
                errors["promo_code"] = (
                    "Бесплатная доставка — только по промокоду (автоматическая уже "
                    "есть в зонах доставки через «Бесплатно от суммы»)."
                )
            if self.scope != PromoScope.CART:
                errors["scope"] = "Бесплатная доставка применяется к корзине (scope=cart)."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "Окончание должно быть позже начала."
        if errors:
            raise ValidationError(errors)
