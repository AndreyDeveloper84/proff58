"""Отзывы покупателей с обязательной модерацией (#573).

Один отзыв на заказ (OneToOne): три оценки (товары/доставка/магазин) + текст.
Публично видны ТОЛЬКО ``approved`` — и только снапшот-поля (``author_name``),
никаких ПДн. Право на отзыв проверяет сервисный слой (``services.create_review``)
через мост ``apps.orders.reviews_bridge`` — в таблицу заказов напрямую модуль
не ходит (CLAUDE.md §4).

Гостевые отзывы — future scope: ``author`` nullable как задел, но создание
сейчас только для аутентифицированного владельца заказа.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class ReviewStatus(models.TextChoices):
    PENDING = "pending", _("На модерации")
    APPROVED = "approved", _("Опубликован")
    REJECTED = "rejected", _("Отклонён")


class ReviewQuerySet(models.QuerySet):
    def approved(self) -> ReviewQuerySet:
        return self.filter(status=ReviewStatus.APPROVED)


def _rating_field(verbose):
    return models.PositiveSmallIntegerField(
        verbose, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )


class Review(TimeStampedModel):
    """Отзыв по завершённому заказу (право на отзыв — см. services.create_review)."""

    order = models.OneToOneField(
        "orders.Order", on_delete=models.CASCADE, related_name="review", verbose_name=_("Заказ")
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
        verbose_name=_("Автор"),
    )
    author_name = models.CharField(
        _("Публичное имя"),
        max_length=150,
        blank=True,
        help_text=_("Снапшот («Имя И.»): публичный API отдаёт только его, не ПДн автора."),
    )
    product_rating = _rating_field(_("Оценка товаров"))
    delivery_rating = _rating_field(_("Оценка доставки"))
    shop_rating = _rating_field(_("Оценка магазина"))
    text = models.TextField(_("Текст"), blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )
    rejection_reason = models.TextField(_("Причина отклонения"), blank=True)
    moderated_at = models.DateTimeField(_("Промодерирован"), null=True, blank=True)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        verbose_name = _("Отзыв")
        verbose_name_plural = _("Отзывы")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="reviews_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Отзыв по заказу {self.order_id} ({self.get_status_display()})"

    @property
    def is_approved(self) -> bool:
        return self.status == ReviewStatus.APPROVED
