"""Модели каталога товаров.

Сайт — мастер по контенту: категории, атрибуты (EAV), товары, фото.
1С — мастер по цене, остатку и коду номенклатуры. Связь через code_1c / article.

Дерево категорий строится на django-treebeard (MP_Node):
быстрые запросы потомков/предков без рекурсивных JOIN-ов.
"""

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from treebeard.mp_tree import MP_Node


class Category(MP_Node):
    """Категория каталога. Поддерживает произвольную глубину вложенности."""

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


class Product(models.Model):
    """Товар. Контентная сторона данных.

    Поля code_1c и article — «интерфейс» к 1С: оба nullable,
    заполняются в процессе линковки импортированных данных.
    """

    # --- Ссылки на 1С (заполняются при линковке) ---
    code_1c = models.CharField(
        _("Код 1С"),
        max_length=50,
        blank=True,
        db_index=True,
        help_text=_("Внутренний код номенклатуры 1С. Заполняется автоматически при синхронизации."),
    )
    article = models.CharField(
        _("Артикул"),
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_("Товарный артикул (SKU). Может совпадать с артикулом поставщика."),
    )

    # --- Контент ---
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("Категория"),
    )
    name = models.CharField(_("Название"), max_length=512)
    slug = models.SlugField(_("Slug"), max_length=512, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    short_description = models.CharField(_("Краткое описание"), max_length=512, blank=True)

    # --- SEO ---
    meta_title = models.CharField(_("Meta title"), max_length=255, blank=True)
    meta_description = models.CharField(_("Meta description"), max_length=512, blank=True)

    # --- Статус ---
    is_active = models.BooleanField(_("Активен"), default=True)

    # --- Кэш атрибутов для быстрой фасетной фильтрации ---
    attrs_cache = models.JSONField(
        _("Кэш характеристик"),
        default=dict,
        blank=True,
        help_text=_("Денормализованный JSON значений характеристик. Обновляется автоматически."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Товар")
        verbose_name_plural = _("Товары")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


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
