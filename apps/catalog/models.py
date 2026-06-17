"""Модели каталога товаров.

Ключевой принцип: структура каталога сайта НЕЗАВИСИМА от иерархии 1С.

  1С (учётная система)        Сайт (продающая система)
  ─────────────────────      ──────────────────────────────
  товар / артикул        →   своя категория / подкатегория
  цена / остаток         →   характеристики / SEO / фото / витрина
  исходная группа (хаос)  ✗   (не управляет структурой сайта)

Связь — по коду 1С (code_1c) и артикулу. Распределение товаров по
категориям сайта выполняется через правила сопоставления
(CategoryMappingRule), а не по группе из 1С. Повторный импорт из 1С
обновляет только цену/остаток/исходные поля и НЕ трогает ручную работу
(категорию сайта, витринное название, описание, SEO, фото).

Дерево категорий — django-treebeard (MP_Node): быстрые запросы
потомков/предков без рекурсивных JOIN-ов.
"""

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from treebeard.mp_tree import MP_Node

from apps.core.models import TimeStampedModel


class Category(MP_Node):
    """Категория каталога сайта. Произвольная глубина вложенности."""

    name = models.CharField(_("Название"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=255, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    image = models.ImageField(_("Изображение"), upload_to="categories/", blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)
    meta_title = models.CharField(_("Meta title"), max_length=255, blank=True)
    meta_description = models.CharField(_("Meta description"), max_length=512, blank=True)

    node_order_by = ["sort_order", "name"]

    class Meta:
        verbose_name = _("Категория")
        verbose_name_plural = _("Категории")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class AttributeType(models.TextChoices):
    TEXT = "text", _("Текст")
    INTEGER = "integer", _("Целое число")
    DECIMAL = "decimal", _("Число с точкой")
    BOOLEAN = "boolean", _("Да/Нет")
    SELECT = "select", _("Список (одно значение)")
    MULTISELECT = "multiselect", _("Список (несколько значений)")


class Attribute(models.Model):
    """Характеристика товара (тип, единица измерения)."""

    slug = models.SlugField(_("Slug"), max_length=100, unique=True)
    name = models.CharField(_("Название"), max_length=255)
    attribute_type = models.CharField(
        _("Тип"), max_length=12, choices=AttributeType.choices, default=AttributeType.TEXT
    )
    unit = models.CharField(_("Единица измерения"), max_length=32, blank=True)
    is_filterable = models.BooleanField(_("Показывать в фильтре"), default=False)
    is_comparable = models.BooleanField(_("Показывать в сравнении"), default=False)

    class Meta:
        verbose_name = _("Характеристика")
        verbose_name_plural = _("Характеристики")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AttributeOption(models.Model):
    """Вариант значения для SELECT/MULTISELECT-характеристик."""

    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="options")
    value = models.CharField(_("Значение"), max_length=255)
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)

    class Meta:
        verbose_name = _("Вариант характеристики")
        verbose_name_plural = _("Варианты характеристик")
        ordering = ["sort_order", "value"]
        unique_together = [("attribute", "value")]

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.value}"


class CategoryAttribute(models.Model):
    """Привязка характеристики к категории с метаданными отображения."""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="category_attributes"
    )
    attribute = models.ForeignKey(
        Attribute, on_delete=models.CASCADE, related_name="category_attributes"
    )
    is_required = models.BooleanField(_("Обязательна"), default=False)
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)

    class Meta:
        verbose_name = _("Характеристика категории")
        verbose_name_plural = _("Характеристики категорий")
        ordering = ["sort_order"]
        unique_together = [("category", "attribute")]

    def __str__(self) -> str:
        return f"{self.category} → {self.attribute}"


class MappingRuleType(models.TextChoices):
    ARTICLE = "article", _("По артикулу (точное совпадение)")
    NAME_CONTAINS = "name_contains", _("По слову в названии")
    BRAND_PREFIX = "brand_prefix", _("По бренду + серии модели")
    SOURCE_GROUP = "source_group", _("По исходной группе 1С")


class CategoryMappingRule(models.Model):
    """Правило автораспределения товаров 1С по категориям сайта.

    Применяются по возрастанию priority; первое сработавшее правило
    назначает категорию. Если ни одно не сработало — товар уходит
    в «Неразобранные» (category=None, status=needs_review).
    """

    rule_type = models.CharField(_("Тип правила"), max_length=20, choices=MappingRuleType.choices)
    pattern = models.CharField(
        _("Образец"),
        max_length=255,
        help_text=_(
            "Артикул / слово в названии / серия модели / название группы 1С — "
            "в зависимости от типа правила."
        ),
    )
    brand = models.CharField(
        _("Бренд"),
        max_length=100,
        blank=True,
        help_text=_("Только для типа «бренд + серия»: например, Bosch."),
    )
    target_category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="mapping_rules",
        verbose_name=_("Категория сайта"),
    )
    priority = models.PositiveSmallIntegerField(
        _("Приоритет"), default=100, help_text=_("Меньше = раньше применяется.")
    )
    is_active = models.BooleanField(_("Активно"), default=True)
    note = models.CharField(_("Комментарий"), max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Правило сопоставления")
        verbose_name_plural = _("Правила сопоставления")
        ordering = ["priority", "id"]

    def __str__(self) -> str:
        return f"[{self.get_rule_type_display()}] {self.pattern} → {self.target_category}"


class ProductStatus(models.TextChoices):
    IMPORTED = "imported", _("Импортирован (не разобран)")
    NEEDS_REVIEW = "needs_review", _("Требует проверки")
    DRAFT = "draft", _("Черновик")
    PUBLISHED = "published", _("Опубликован")


class StockStatus(models.TextChoices):
    IN_STOCK = "in_stock", _("В наличии")
    OUT_OF_STOCK = "out_of_stock", _("Нет в наличии")
    ON_ORDER = "on_order", _("Под заказ")


class Product(TimeStampedModel):
    """Товар.

    Идентичность из 1С: code_1c (внутренний код / external_id) и article (SKU).
    Контент сайта (категория, витринное название, SEO, фото) ведётся отдельно
    и защищён от перезаписи при повторном импорте — см. apps.sync_1c.importer.
    """

    # --- Идентификаторы из 1С ---
    code_1c = models.CharField(
        _("Код 1С (external_id)"),
        max_length=50,
        null=True,
        blank=True,
        unique=True,
        help_text=_("Внутренний код/идентификатор номенклатуры 1С. Главный ключ связи."),
    )
    article = models.CharField(_("Артикул (SKU)"), max_length=100, blank=True, db_index=True)
    barcode = models.CharField(_("Штрихкод"), max_length=64, blank=True)

    # --- Данные из 1С (обновляются импортом, не редактируются вручную) ---
    original_name = models.CharField(
        _("Название в 1С"),
        max_length=512,
        blank=True,
        help_text=_("Исходное название из 1С. Обновляется импортом, на витрине не используется."),
    )
    source_group = models.CharField(
        _("Исходная группа 1С"),
        max_length=255,
        blank=True,
        help_text=_("Группа товара в 1С (справочно). Структуру сайта не определяет."),
    )
    unit = models.CharField(_("Единица измерения"), max_length=32, blank=True)
    is_active_1c = models.BooleanField(_("Активен в 1С"), null=True, blank=True)

    # --- Контент сайта (ведётся вручную, импорт НЕ трогает) ---
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("Категория сайта"),
        help_text=_("Пусто = «Неразобранные». Назначается правилом или вручную."),
    )
    category_is_manual = models.BooleanField(
        _("Категория назначена вручную"),
        default=False,
        help_text=_("Если да — авторазбор её больше не меняет."),
    )
    matched_rule = models.ForeignKey(
        CategoryMappingRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_products",
        verbose_name=_("Сработавшее правило"),
    )
    brand = models.CharField(_("Бренд"), max_length=100, blank=True, db_index=True)
    name = models.CharField(_("Название (витрина)"), max_length=512)
    slug = models.SlugField(_("Slug"), max_length=512, unique=True, blank=True)
    description = models.TextField(_("Описание"), blank=True)
    short_description = models.CharField(_("Краткое описание"), max_length=512, blank=True)
    meta_title = models.CharField(_("Meta title"), max_length=255, blank=True)
    meta_description = models.CharField(_("Meta description"), max_length=512, blank=True)

    # --- Цена и остаток (источник истины — 1С, денормализовано для витрины) ---
    price = models.DecimalField(_("Цена"), max_digits=14, decimal_places=2, null=True, blank=True)
    old_price = models.DecimalField(
        _("Старая цена"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    stock_quantity = models.DecimalField(_("Остаток"), max_digits=14, decimal_places=3, default=0)
    reserved_quantity = models.DecimalField(_("Резерв"), max_digits=14, decimal_places=3, default=0)
    available_quantity = models.DecimalField(
        _("Доступно"), max_digits=14, decimal_places=3, default=0
    )
    stock_status = models.CharField(
        _("Наличие"), max_length=12, choices=StockStatus.choices, default=StockStatus.OUT_OF_STOCK
    )
    price_updated_at = models.DateTimeField(_("Цена обновлена"), null=True, blank=True)
    stock_updated_at = models.DateTimeField(_("Остаток обновлён"), null=True, blank=True)

    # --- Жизненный цикл ---
    status = models.CharField(
        _("Статус"),
        max_length=14,
        choices=ProductStatus.choices,
        default=ProductStatus.IMPORTED,
        db_index=True,
    )
    is_active = models.BooleanField(
        _("Показывать на сайте"),
        default=False,
        help_text=_("Виден на витрине только если статус «Опубликован» и этот флаг включён."),
    )

    attrs_cache = models.JSONField(
        _("Кэш характеристик"),
        default=dict,
        blank=True,
        help_text=_("Денормализованный JSON значений характеристик для фасетных фильтров."),
    )

    class Meta:
        verbose_name = _("Товар")
        verbose_name_plural = _("Товары")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "category"]),
        ]

    def __str__(self) -> str:
        return self.name or self.original_name or (self.article or "товар")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_unique_slug()
        super().save(*args, **kwargs)

    def _build_unique_slug(self) -> str:
        """Slug из имени/идентификаторов с числовым суффиксом при коллизии.

        Нужен при массовом импорте из 1С: товары часто приходят с одинаковым
        витринным именем («Дрель», «Дрель»), а поле slug уникально. Без
        дедупликации второй такой товар падает на unique-констрейнте.
        """
        max_length = self._meta.get_field("slug").max_length
        suffix_reserved = 12  # запас под "-9999999999"

        base = ""
        for value in (self.name, self.original_name, self.article, self.code_1c, "tovar"):
            base = slugify(value or "", allow_unicode=True)
            if base:
                break
        base = base[: max_length - suffix_reserved] or "tovar"

        slug = base
        n = 2
        while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            suffix = f"-{n}"
            slug = f"{base[: max_length - len(suffix)]}{suffix}"
            n += 1
        return slug

    @property
    def is_visible(self) -> bool:
        """Виден ли товар на витрине."""
        return self.is_active and self.status == ProductStatus.PUBLISHED

    def recalc_stock_status(self) -> None:
        """Пересчитать статус наличия по доступному остатку."""
        if self.available_quantity and self.available_quantity > 0:
            self.stock_status = StockStatus.IN_STOCK
        else:
            self.stock_status = StockStatus.OUT_OF_STOCK


class ProductImage(models.Model):
    """Изображение товара."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(_("Файл"), upload_to="products/")
    alt = models.CharField(_("Alt-текст"), max_length=255, blank=True)
    is_main = models.BooleanField(_("Главное фото"), default=False)
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)

    class Meta:
        verbose_name = _("Изображение товара")
        verbose_name_plural = _("Изображения товаров")
        ordering = ["-is_main", "sort_order"]

    def __str__(self) -> str:
        return f"Фото {self.product} #{self.pk}"


class ProductAttributeValue(models.Model):
    """Значение характеристики конкретного товара (EAV-строка)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)

    value_text = models.TextField(_("Текст"), blank=True)
    value_integer = models.BigIntegerField(_("Целое"), null=True, blank=True)
    value_decimal = models.DecimalField(
        _("Число"), max_digits=18, decimal_places=4, null=True, blank=True
    )
    value_boolean = models.BooleanField(_("Булево"), null=True, blank=True)
    value_option = models.ForeignKey(
        AttributeOption, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = _("Значение характеристики")
        verbose_name_plural = _("Значения характеристик")
        unique_together = [("product", "attribute")]

    def __str__(self) -> str:
        return f"{self.product} | {self.attribute}"

    @property
    def value(self):
        """Возвращает фактическое значение в зависимости от типа атрибута."""
        t = self.attribute.attribute_type
        if t == AttributeType.TEXT:
            return self.value_text
        if t == AttributeType.INTEGER:
            return self.value_integer
        if t == AttributeType.DECIMAL:
            return self.value_decimal
        if t == AttributeType.BOOLEAN:
            return self.value_boolean
        if t in (AttributeType.SELECT, AttributeType.MULTISELECT):
            return self.value_option
        return None
