"""Отзывы покупателей с премодерацией (#72).

Единая модель Review с subject_type для расширения (отзывы о заказе/сервисе
добавляются тем же модулем без нового приложения).
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class SubjectType(models.TextChoices):
    PRODUCT = "product", _("Товар")
    ORDER = "order", _("Заказ")


class ReviewStatus(models.TextChoices):
    PENDING = "pending", _("На модерации")
    APPROVED = "approved", _("Одобрен")
    REJECTED = "rejected", _("Отклонён")


class ReviewQuerySet(models.QuerySet):
    def approved(self) -> ReviewQuerySet:
        return self.filter(status=ReviewStatus.APPROVED)

    def for_product(self, product_id: int) -> ReviewQuerySet:
        return self.filter(subject_type=SubjectType.PRODUCT, subject_id=product_id)


class Review(TimeStampedModel):
    """Отзыв покупателя о товаре (или другом объекте в будущем)."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
        verbose_name=_("Автор"),
    )
    author_name = models.CharField(_("Имя автора"), max_length=150, blank=True)
    subject_type = models.CharField(
        _("Тип объекта"),
        max_length=20,
        choices=SubjectType.choices,
        default=SubjectType.PRODUCT,
        db_index=True,
    )
    subject_id = models.PositiveIntegerField(_("ID объекта"), db_index=True)
    rating = models.PositiveSmallIntegerField(
        _("Оценка"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    body = models.TextField(_("Текст отзыва"), blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )
    moderated_at = models.DateTimeField(_("Дата модерации"), null=True, blank=True)

    objects: ReviewQuerySet = ReviewQuerySet.as_manager()

    class Meta:
        verbose_name = _("Отзыв")
        verbose_name_plural = _("Отзывы")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["subject_type", "subject_id", "status"],
                name="reviews_subject_status_idx",
            ),
        ]

    def __str__(self) -> str:
        author = self.author_name or (self.author.get_full_name() if self.author else "Аноним")
        return f"[{self.rating}★] {author} → {self.subject_type}#{self.subject_id}"

    @property
    def is_approved(self) -> bool:
        return self.status == ReviewStatus.APPROVED
