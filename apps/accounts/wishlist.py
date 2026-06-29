"""Избранное (wishlist) — хранится в модели WishlistItem (#329)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from apps.core.models import TimeStampedModel


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist",
        db_constraint=False,
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, db_constraint=False)

    class Meta:
        verbose_name = _("Избранное")
        verbose_name_plural = _("Избранное")
        unique_together = [("user", "product")]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"
