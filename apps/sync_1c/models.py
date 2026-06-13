"""Модели слоя синхронизации с 1С 7.7.

Принцип изоляции: 1С не знает ничего о нашем каталоге, каталог не знает
ничего о структуре 1С. Этот слой — единственное место, где они встречаются.

Поток данных:
  1С → (любой формат: DBF / XML / текстовый файл)
    → NomenclatureStaging (raw_payload + распознанные поля)
    → задача линковки → Product.code_1c / Product.article
    → PriceRecord / StockRecord (читаются при отдаче товара)

Когда станет известна точная структура 1С, меняем только парсер
(management command / Celery task), не трогая модели каталога.
"""

import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _


class StagingStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает обработки")
    MATCHED = "matched", _("Привязан к товару")
    NEW = "new", _("Новый товар (не привязан)")
    ERROR = "error", _("Ошибка парсинга")


class NomenclatureStaging(models.Model):
    """Сырая запись из выгрузки 1С.

    raw_payload хранит исходные данные как есть (DBF-строка → dict,
    XML-узел → dict и т.п.). Структурированные поля заполняются парсером
    по мере того, как мы разбираемся со структурой конкретной базы 1С.
    """

    # Идентификаторы из 1С — единственные «ключи» связи
    code_1c = models.CharField(_("Код 1С"), max_length=50, db_index=True)
    article = models.CharField(_("Артикул"), max_length=100, blank=True, db_index=True)

    # Исходные данные — не трогаем после вставки
    raw_payload = models.JSONField(
        _("Исходные данные"),
        default=dict,
        encoder=DjangoJSONEncoder,
        help_text=_("Все поля строки/узла из выгрузки 1С в исходном виде."),
    )

    # Поля, распознанные парсером (nullable — пока не знаем полную схему)
    name_1c = models.CharField(_("Название в 1С"), max_length=512, blank=True)
    unit = models.CharField(_("Единица измерения"), max_length=32, blank=True)
    price = models.DecimalField(
        _("Цена (из выгрузки)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    stock = models.DecimalField(
        _("Остаток (из выгрузки)"), max_digits=14, decimal_places=3, null=True, blank=True
    )
    is_active_1c = models.BooleanField(
        _("Активен в 1С"), null=True, blank=True, help_text=_("None = поле не найдено в выгрузке.")
    )

    # Статус обработки
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=StagingStatus.choices,
        default=StagingStatus.PENDING,
        db_index=True,
    )
    error_message = models.TextField(_("Сообщение об ошибке"), blank=True)

    # Связь с товаром каталога (заполняется задачей линковки)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staging_records",
        verbose_name=_("Товар каталога"),
    )

    # Трассировка происхождения строки (для расследования и дедупликации).
    sync_log = models.ForeignKey(
        "SyncLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rows",
        verbose_name=_("Прогон импорта"),
    )
    source_file = models.CharField(_("Файл-источник"), max_length=255, blank=True)
    row_hash = models.CharField(
        _("Хэш строки"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("SHA-256 от raw_payload — для выявления повторных строк."),
    )

    imported_at = models.DateTimeField(_("Время импорта"), auto_now_add=True)
    processed_at = models.DateTimeField(_("Время обработки"), null=True, blank=True)

    class Meta:
        verbose_name = _("Запись выгрузки 1С")
        verbose_name_plural = _("Записи выгрузки 1С")
        ordering = ["-imported_at"]
        indexes = [
            models.Index(fields=["status", "imported_at"]),
        ]

    def __str__(self) -> str:
        return f"1С [{self.code_1c}] {self.name_1c or '—'}"


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


class StockRecord(models.Model):
    """Остаток товара по складу из 1С."""

    code_1c = models.CharField(_("Код 1С"), max_length=50, db_index=True)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_records",
        verbose_name=_("Товар"),
    )
    warehouse = models.CharField(
        _("Склад"), max_length=100, default="main", help_text=_("Код или название склада из 1С.")
    )
    quantity = models.DecimalField(_("Количество"), max_digits=14, decimal_places=3)
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Остаток из 1С")
        verbose_name_plural = _("Остатки из 1С")
        unique_together = [("code_1c", "warehouse")]
        indexes = [
            models.Index(fields=["code_1c", "warehouse"]),
        ]

    def __str__(self) -> str:
        return f"{self.code_1c} | {self.warehouse}: {self.quantity}"


class SyncLog(models.Model):
    """Журнал запусков синхронизации."""

    class SyncType(models.TextChoices):
        FULL = "full", _("Полная выгрузка")
        PRICES = "prices", _("Цены")
        STOCK = "stock", _("Остатки")
        ORDERS = "orders", _("Заказы")

    class SyncResult(models.TextChoices):
        OK = "ok", _("Успешно")
        PARTIAL = "partial", _("Частично")
        ERROR = "error", _("Ошибка")

    batch_uid = models.UUIDField(_("UID прогона"), default=uuid.uuid4, editable=False, unique=True)
    sync_type = models.CharField(_("Тип"), max_length=10, choices=SyncType.choices)
    source_file = models.CharField(
        _("Файл-источник"), max_length=255, blank=True, help_text=_("Имя файла/период выгрузки.")
    )
    result = models.CharField(_("Результат"), max_length=10, choices=SyncResult.choices)
    rows_total = models.PositiveIntegerField(_("Всего строк"), default=0)
    rows_ok = models.PositiveIntegerField(_("Обработано"), default=0)
    rows_error = models.PositiveIntegerField(_("Ошибок"), default=0)
    error_details = models.TextField(_("Детали ошибок"), blank=True)
    started_at = models.DateTimeField(_("Начало"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Конец"), null=True, blank=True)

    class Meta:
        verbose_name = _("Лог синхронизации")
        verbose_name_plural = _("Логи синхронизации")
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.get_sync_type_display()} {self.started_at:%Y-%m-%d %H:%M} → {self.result}"
