"""Модели домена ценообразования.

``PriceRecord`` — владелец истории и типов цен (опт/розница) внутри домена
``pricing``. Слой ``sync_1c`` обновляет цены (пишет записи), но не владеет
моделью: домен цены принадлежит ``pricing``.

Историческое имя таблицы (``sync_1c_pricerecord``) сохранено через
``db_table`` — данные физически не переносятся, меняется только владелец
модели в состоянии Django (см. миграции SeparateDatabaseAndState).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class PriceRecord(models.Model):
    """Актуальная цена из 1С.

    Хранит последнюю известную цену по коду 1С.
    При получении новой записи старая помечается is_current=False.
    price_type позволит добавить оптовые/розничные цены без миграции.
    """

    code_1c = models.CharField(_("Код 1С"), max_length=50, db_index=True)
    # FK на Product nullable: цена может прийти до линковки
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_records",
        verbose_name=_("Товар"),
    )
    price_type = models.CharField(
        _("Тип цены"),
        max_length=50,
        default="retail",
        help_text=_("retail / wholesale / promo или код типа цены из 1С."),
    )
    value = models.DecimalField(_("Цена"), max_digits=14, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    is_current = models.BooleanField(_("Актуальная"), default=True, db_index=True)
    valid_from = models.DateTimeField(_("Действует с"), auto_now_add=True)

    class Meta:
        verbose_name = _("Цена из 1С")
        verbose_name_plural = _("Цены из 1С")
        db_table = "sync_1c_pricerecord"
        ordering = ["-valid_from"]
        indexes = [
            models.Index(fields=["code_1c", "price_type", "is_current"]),
        ]
        constraints = [
            # Не более одной актуальной цены на (код 1С, тип цены, валюта).
            models.UniqueConstraint(
                fields=["code_1c", "price_type", "currency"],
                condition=models.Q(is_current=True),
                name="uniq_current_price_per_code_type_currency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code_1c} | {self.price_type}: {self.value} {self.currency}"
