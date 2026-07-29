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

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import (
    CheckConstraint,
    F,
    Index,
    Q,
    UniqueConstraint,
)
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from treebeard.mp_tree import MP_Node

from apps.core.models import TimeStampedModel


class Source(models.TextChoices):
    """Источник значения характеристики. Значения совпадают с ключами карты
    ``source_priority`` в ``data/attribute_rules.json``; приоритет перезаписи
    берётся оттуда (см. apps.catalog.management.commands.enrich_attributes).
    """

    MANUAL = "manual", _("Вручную")
    IMPORT_1C = "import_1c", _("Импорт 1С")
    REGEX = "regex", _("Regex по названию")
    KEYWORD = "keyword", _("Ключевое слово")
    RULES = "rules", _("Правила каталога")
    LLM = "llm", _("AI/LLM")
    INFERRED = "inferred", _("Инференс по атрибутам")
    WEB = "web", _("Web-поиск")
    MARKETPLACE = "marketplace", _("Маркетплейс")


class Category(MP_Node):
    """Категория каталога сайта. Произвольная глубина вложенности."""

    name = models.CharField(_("Название"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=255, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    image = models.ImageField(_("Изображение"), upload_to="categories/", blank=True)
    hero_image = models.ImageField(_("Hero: фон"), upload_to="categories/hero/", blank=True)
    hero_eyebrow = models.CharField(_("Hero: слоган"), max_length=120, blank=True)
    hero_cta_label = models.CharField(_("Hero: текст кнопки"), max_length=60, blank=True)
    hero_cta_href = models.CharField(_("Hero: ссылка кнопки"), max_length=512, blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)
    on_site = models.BooleanField(
        _("Показывать на сайте"),
        default=True,
        help_text=_("False — группа 1С не размещается на витрине (под скрытым корнем)."),
    )
    external_id_1c = models.CharField(
        _("Код группы 1С"),
        max_length=50,
        null=True,
        blank=True,
        unique=True,
        help_text=_(
            "external_id группы 1С для листа дерева. Единственная связь категории "
            "с учётной системой (ADR-0002). Узлы-контейнеры остаются пустыми."
        ),
    )
    is_site_v2 = models.BooleanField(
        _("Узел витрины v2"),
        default=False,
        db_index=True,
        help_text=_(
            "True — узел курируемого v2-дерева сайта (создан build_skeleton/build_section). "
            "Отличает витринное дерево от легаси-категорий, зеркалящих группы 1С. Раздел "
            "«Категории (сайт)» показывает только такие узлы."
        ),
    )
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)
    meta_title = models.CharField(_("Meta title"), max_length=255, blank=True)
    meta_description = models.CharField(_("Meta description"), max_length=512, blank=True)

    node_order_by = ["sort_order", "name"]

    class Meta:
        verbose_name = _("Категория")
        verbose_name_plural = _("Категории")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        """Адрес категории на витрине (Next.js `/catalog/[category]`).

        Нужен кнопке «Смотреть на сайте» в админке: витрина и админка живут за
        одним nginx на одном хосте, поэтому путь относительный.
        """
        return f"/catalog/{self.slug}"

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
    is_ai_feature = models.BooleanField(
        _("AI-характеристика"),
        default=False,
        help_text=_("Плохо извлекается regex/словарём из названия — кандидат на добор LLM (#62)."),
    )

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
    slug = models.SlugField(
        _("Slug"),
        max_length=120,
        blank=True,
        help_text=_("ЧПУ-идентификатор варианта (для SEO-фасетов вида ?tool_type=perforatory)."),
    )
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)

    class Meta:
        verbose_name = _("Вариант характеристики")
        verbose_name_plural = _("Варианты характеристик")
        ordering = ["sort_order", "value"]
        unique_together = [("attribute", "value")]
        constraints = [
            models.UniqueConstraint(
                fields=["attribute", "slug"],
                condition=~models.Q(slug=""),
                name="uniq_attributeoption_attr_slug_nonempty",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.value}"


class FacetGroup(models.TextChoices):
    """Раздел фильтра в сайдбаре витрины (§22.4). «Базовые» (бренд/наличие/цена/тип
    питания) и навигация (tool_type) определяются отдельно, поэтому здесь только две
    группы технических фильтров: основные и дополнительные (последние сворачиваются)."""

    MAIN = "main", _("Основные")
    EXTRA = "extra", _("Дополнительные")


class CategoryAttribute(models.Model):
    """Привязка характеристики к категории с метаданными отображения."""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="category_attributes"
    )
    attribute = models.ForeignKey(
        Attribute, on_delete=models.CASCADE, related_name="category_attributes"
    )
    is_required = models.BooleanField(_("Обязательна"), default=False)
    is_filter = models.BooleanField(
        _("Использовать в фильтре"),
        default=True,
        help_text=_("Характеристика участвует в фасетных фильтрах этой категории."),
    )
    group = models.CharField(
        _("Группа фильтра"),
        max_length=8,
        choices=FacetGroup.choices,
        default=FacetGroup.MAIN,
        help_text=_(
            "Раздел в сайдбаре: «Основные» или «Дополнительные» (свёрнуты по умолчанию). "
            "Куратор переносит сюда второстепенные характеристики (вход — coverage-отчёт #225)."
        ),
    )
    is_seo_facet = models.BooleanField(
        _("SEO-фасет"),
        default=False,
        help_text=_("На основе значений строятся посадочные страницы (вторая ось навигации)."),
    )
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
    REGEX = "regex", _("По регулярному выражению (имя)")
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
    exclude_pattern = models.CharField(
        _("Исключение (regex по имени)"),
        max_length=255,
        blank=True,
        help_text=_(
            "Негативный guard: если выражение найдено в названии — правило НЕ "
            "срабатывает (напр. «бур», но исключить «бурения земл|мотобур»)."
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


class OneCGroupStatus(models.TextChoices):
    ACTIVE = "active", _("Активна (есть товары)")
    STALE = "stale", _("Пустая (нет товаров)")
    DISCOVERED = "discovered", _("Найдена в выгрузке (нет в маппинге)")


# Разделитель материализованного пути групп 1С (unit separator — сортируется раньше
# печатных символов, поэтому родитель идёт перед детьми в pre-order).
ONEC_TREE_SEP = "\x1f"


class OneCGroup(models.Model):
    """Группа номенклатуры 1С — отдельный реестр (НЕ часть дерева сайта).

    Источник истины: ``data/group_mapping.json`` (код ``external_id`` + имя ``group_1c``
    + ``site_path``); живость/счётчики — по ``Product.source_group`` (последняя выгрузка).
    Синкается командой ``catalog_sync_1c_groups``. Связь с категорией сайта — через
    ``mapped_category`` и правила сопоставления (см. ``GroupCategoryMap``).

    Статусы: ``active`` — есть товары; ``stale`` — была в маппинге, но товаров нет;
    ``discovered`` — встретилась в ``source_group``, но в маппинге её нет (надо сопоставить).
    Принцип: 1С — источник, сайт — мастер структуры; пере-импорт дерево сайта не меняет.
    """

    code = models.CharField(_("Код 1С (external_id)"), max_length=50, blank=True, db_index=True)
    name = models.CharField(_("Имя группы 1С"), max_length=255, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Родительская группа 1С"),
    )
    tree_path = models.CharField(
        _("Путь в дереве 1С"),
        max_length=1024,
        blank=True,
        db_index=True,
        # db_collation="C" — побайтовая сортировка: разделитель \x1f (0x1f) меньше пробела
        # и любых букв, поэтому родитель идёт строго перед детьми (pre-order). Локальная
        # UTF-8-коллация игнорирует управляющие символы и ломала бы вложенность.
        db_collation="C",
        help_text=_("Материализованный путь имён (для древовидной сортировки админки)."),
    )
    site_path = models.JSONField(_("Путь на сайте (из маппинга)"), default=list, blank=True)
    mapped_category = models.ForeignKey(
        "Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onec_groups",
        verbose_name=_("Категория сайта"),
    )
    product_count = models.PositiveIntegerField(_("Товаров (по source_group)"), default=0)
    status = models.CharField(
        _("Статус"),
        max_length=12,
        choices=OneCGroupStatus.choices,
        default=OneCGroupStatus.DISCOVERED,
        db_index=True,
    )
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Группа 1С")
        verbose_name_plural = _("Группы 1С")
        ordering = ["name"]
        indexes = [models.Index(fields=["status", "name"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.code or '—'})"


class GroupCategoryMapping(OneCGroup):
    """Proxy-вид OneCGroup для отдельного раздела админки «Сопоставление групп и категорий».

    Та же таблица, что и «Группы 1С», но админка сфокусирована на правке
    ``mapped_category`` (группа → категория сайта) и действии «применить» (расставить
    товары группы по ``source_group`` в выбранную категорию). Своей таблицы не создаёт.
    """

    class Meta:
        proxy = True
        verbose_name = _("Сопоставление группы и категории")
        verbose_name_plural = _("Сопоставление групп и категорий")


class SiteCategory(Category):
    """Proxy-вид Category для раздела админки «Категории (сайт)».

    Показывает ТОЛЬКО курируемое v2-дерево (поддеревья корней-разделов из
    ``semantic.SECTION_RULES``), без легаси-категорий, зеркалящих группы 1С.
    Та же таблица, что и «Категории»; фильтрация — в админке.
    """

    class Meta:
        proxy = True
        verbose_name = _("Категория (сайт)")
        verbose_name_plural = _("Категории (сайт)")


class ProductStatus(models.TextChoices):
    IMPORTED = "imported", _("Импортирован (не разобран)")
    NEEDS_REVIEW = "needs_review", _("Требует проверки")
    DRAFT = "draft", _("Черновик")
    PUBLISHED = "published", _("Опубликован")


class StockStatus(models.TextChoices):
    IN_STOCK = "in_stock", _("В наличии")
    OUT_OF_STOCK = "out_of_stock", _("Нет в наличии")
    ON_ORDER = "on_order", _("Под заказ")


class EnrichStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает")
    IN_QUEUE = "in_queue", _("В очереди")
    DONE = "done", _("Готово")
    MODERATION = "moderation", _("На модерации")
    FAILED = "failed", _("Ошибка")


class ContentSource(models.TextChoices):
    MANUAL = "manual", _("Вручную")
    IMPORT_1C = "import_1c", _("Импорт 1С")
    LLM = "llm", _("AI-генерация")
    WEB = "web", _("Web-поиск")
    MARKETPLACE = "marketplace", _("Маркетплейс")


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
    content_locked = models.BooleanField(
        _("Контент защищён"),
        default=False,
        help_text=_(
            "Если включено — импорт из 1С не перезаписывает контентные поля "
            "(витринное название, описание, SEO). ADR: 1С не затирает ручную работу."
        ),
    )
    enrich_status = models.CharField(
        _("Статус обогащения"),
        max_length=12,
        choices=EnrichStatus.choices,
        default=EnrichStatus.PENDING,
        db_index=True,
    )
    content_source = models.CharField(
        _("Источник карточного контента"),
        max_length=12,
        choices=ContentSource.choices,
        blank=True,
        default="",
    )
    content_confidence = models.FloatField(_("Уверенность контента"), null=True, blank=True)
    content_field_sources = models.JSONField(
        _("Провенанс карточных полей"),
        default=dict,
        blank=True,
        help_text="{'name':'manual','description':'web'} — истинный источник по полю",
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
    video_url = models.URLField(_("Видео (URL)"), blank=True)
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
            # GIN по attrs_cache — ускоряет фасетные containment-фильтры (attrs_cache @> {...})
            # и has_key. Сам GROUP BY не ускоряет (его сужает фильтр+категория).
            GinIndex(fields=["attrs_cache"], name="catalog_product_attrs_gin"),
            # Trigram-GIN (pg_trgm) для поиска по каталогу (#52): ускоряет icontains
            # и trigram_similar (typo-tolerance) по name/article/brand. Требует
            # расширения pg_trgm — оно создаётся в миграции 0007 ПЕРЕД индексами.
            GinIndex(fields=["name"], opclasses=["gin_trgm_ops"], name="catalog_product_name_trgm"),
            GinIndex(
                fields=["article"], opclasses=["gin_trgm_ops"], name="catalog_product_article_trgm"
            ),
            GinIndex(
                fields=["brand"], opclasses=["gin_trgm_ops"], name="catalog_product_brand_trgm"
            ),
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

    def get_absolute_url(self) -> str:
        """Адрес товара на витрине (Next.js `/product/[slug]`).

        Нужен кнопке «Смотреть на сайте» в админке. Витрина отдаёт только
        опубликованное (`visible_products()`), поэтому для черновика ссылка
        приведёт на 404 — предпросмотр черновиков отдельная задача (C1).
        """
        return f"/product/{self.slug}"

    def missing_required_attributes(self) -> list[str]:
        """Имена обязательных характеристик категории, у которых нет значения.

        Проверяется ТОЛЬКО текущая категория товара (без наследования по дереву).
        «Заполнено» определяется через ``attr_value_to_json``: значение считается
        заполненным, если оно не None и не пустая строка (boolean False —
        валидное заполненное значение, см. read_models). Если категория не
        задана — список пуст (правило про категорию проверяется отдельно).
        """
        if not self.category_id or self.pk is None:
            # Без pk нельзя обратиться к attribute_values (новый товар ещё не
            # сохранён). Для нового товара правило применяется в admin.save_related
            # уже после сохранения инлайнов.
            return []

        # Локальный импорт: read_models импортирует модели — избегаем цикла.
        from .read_models import attr_value_to_json

        required = CategoryAttribute.objects.filter(
            category_id=self.category_id, is_required=True
        ).select_related("attribute")

        # Значения товара по attribute_id (один проход; используем prefetch при наличии).
        pav_by_attr = {pav.attribute_id: pav for pav in self.attribute_values.all()}

        missing: list[str] = []
        for ca in required:
            pav = pav_by_attr.get(ca.attribute_id)
            filled = False
            if pav is not None:
                value = attr_value_to_json(pav)
                filled = value is not None and value != ""
            if not filled:
                missing.append(ca.attribute.name)
        return missing

    def publication_errors(self) -> list[str]:
        """Единый источник правил публикации. Пустой список = можно публиковать.

        Цена НЕ проверяется (источник истины — 1С, может временно отсутствовать).
        """
        errors: list[str] = []
        if not self.category_id:
            errors.append("Укажите категорию")
        missing = self.missing_required_attributes()
        if missing:
            errors.append("Заполните обязательные характеристики: " + ", ".join(missing))
        return errors

    def clean(self):
        """Блокируем перевод в «Опубликован» при незаполненных правилах.

        Программные save() из импорта 1С не зовут clean() — импорт не страдает.
        Покрывает редактирование существующего товара через admin-форму.
        """
        super().clean()
        if self.status == ProductStatus.PUBLISHED:
            errors = self.publication_errors()
            if errors:
                raise ValidationError(errors)

    def recalc_stock_status(self) -> None:
        """Пересчитать статус наличия по доступному остатку."""
        if self.available_quantity and self.available_quantity > 0:
            self.stock_status = StockStatus.IN_STOCK
        else:
            self.stock_status = StockStatus.OUT_OF_STOCK


class CompatibilityKind(models.TextChoices):
    ACCESSORY = "accessory", _("Аксессуар / оснастка / расходник")
    COMPATIBLE = "compatible", _("Совместим")


class ProductCompatibility(TimeStampedModel):
    """Явная каталожная связь товар↔товар (движок совместимости, #79).

    Два вида связи:

    * ``ACCESSORY`` — НАПРАВЛЕННАЯ: source — основной товар (инструмент),
      target — аксессуар/оснастка/расходник к нему. Направление значимо и НЕ
      канонизируется: ребро A→B и B→A — это два разных факта (A — аксессуар к B
      и наоборот).
    * ``COMPATIBLE`` — СИММЕТРИЧНАЯ «совместим с». Чтобы не плодить обратные
      дубли (A↔B и B↔A), храним ребро в каноническом виде ``min(id) → max(id)``.

    Канонизация делается в :meth:`clean` и :meth:`save`. ``bulk_create`` обходит
    ``save()`` — массовый импорт совместимостей вне scope V1 (при добавлении
    учесть канонизацию вручную).
    """

    source = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="compat_out",
        verbose_name=_("Товар-источник"),
    )
    target = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="compat_in",
        verbose_name=_("Связанный товар"),
    )
    kind = models.CharField(_("Тип связи"), max_length=20, choices=CompatibilityKind.choices)
    note = models.CharField(_("Примечание"), max_length=512, blank=True)
    sort_order = models.PositiveSmallIntegerField(_("Порядок"), default=0)

    class Meta:
        verbose_name = _("Связь совместимости товаров")
        verbose_name_plural = _("Связи совместимости товаров")
        ordering = ["sort_order", "id"]
        constraints = [
            UniqueConstraint(
                fields=["source", "target", "kind"],
                name="catalog_productcompat_uniq",
            ),
            CheckConstraint(
                check=~Q(source=F("target")),
                name="catalog_productcompat_no_self_link",
            ),
        ]
        indexes = [
            Index(fields=["source", "kind"]),
            Index(fields=["target", "kind"]),
        ]

    def _canonicalize(self) -> None:
        # COMPATIBLE симметричен → храним каноническим min(id)→max(id) (защита от
        # обратных дублей). ACCESSORY направленный — не трогаем.
        if (
            self.kind == CompatibilityKind.COMPATIBLE
            and self.source_id
            and self.target_id
            and self.source_id > self.target_id
        ):
            self.source_id, self.target_id = self.target_id, self.source_id

    @classmethod
    def canonical_pair(cls, source_id, target_id, kind):
        """Каноническая пара (source_id, target_id) для данного вида связи."""
        if (
            kind == CompatibilityKind.COMPATIBLE
            and source_id
            and target_id
            and source_id > target_id
        ):
            return target_id, source_id
        return source_id, target_id

    def clean(self):
        self._canonicalize()
        super().clean()

    def save(self, *args, **kwargs):
        self._canonicalize()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.source} → {self.target} ({self.get_kind_display()})"


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

    # --- Провенанс (откуда значение и насколько ему доверяем) ---
    source = models.CharField(
        _("Источник"),
        max_length=12,
        choices=Source.choices,
        default=Source.MANUAL,
        help_text=_(
            "Приоритет перезаписи берётся из source_priority в attribute_rules.json: "
            "manual не затирается regex/keyword."
        ),
    )
    confidence = models.SmallIntegerField(
        _("Уверенность"),
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_(
            "0–100. Только аналитика/AI, в решении о перезаписи НЕ участвует "
            "(перезапись решает source)."
        ),
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


# ---------------------------------------------------------------------------
# Журналы загрузки и обогащения каталога (видимы в админке)
# ---------------------------------------------------------------------------


class ImportRunStatus(models.TextChoices):
    RUNNING = "running", _("Выполняется")
    DONE = "done", _("Завершён")
    FAILED = "failed", _("Ошибка")


class ImportRun(models.Model):
    """Запуск загрузки/обогащения каталога. Счётчики итогов — в stats (JSONB)."""

    started_at = models.DateTimeField(_("Начат"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Завершён"), null=True, blank=True)
    source = models.CharField(
        _("Источник"), max_length=255, help_text=_("Имя файла / команды запуска.")
    )
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=ImportRunStatus.choices,
        default=ImportRunStatus.RUNNING,
    )
    stats = models.JSONField(
        _("Счётчики"),
        default=dict,
        blank=True,
        help_text=_(
            "categories_created, products_imported, tool_type_assigned, unmatched, "
            "recategorize_flagged, excluded."
        ),
    )

    class Meta:
        verbose_name = _("Запуск импорта")
        verbose_name_plural = _("Запуски импорта")
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.source} @ {self.started_at:%Y-%m-%d %H:%M} [{self.get_status_display()}]"


class EnrichmentResult(models.TextChoices):
    ASSIGNED = "assigned", _("tool_type проставлен")
    MODERATION = "moderation", _("В очередь модерации")
    RECATEGORIZE = "recategorize", _("Сменить категорию")


class EnrichmentLog(models.Model):
    """Решение правил по каждому товару при извлечении tool_type.

    Цель — открыть админку и увидеть, что именно сделали правила: какой
    tool_type проставлен, по какому ключевому слову, либо почему товар ушёл
    в модерацию / на смену категории.
    """

    run = models.ForeignKey(
        ImportRun,
        on_delete=models.CASCADE,
        related_name="enrichment_logs",
        verbose_name=_("Запуск"),
    )
    product_external_id = models.CharField(_("Код 1С товара"), max_length=50, db_index=True)
    raw_name = models.CharField(_("Название из 1С"), max_length=512)
    category_path = models.CharField(_("Путь категории"), max_length=512, blank=True)
    result = models.CharField(
        _("Результат"), max_length=12, choices=EnrichmentResult.choices, db_index=True
    )
    tool_type = models.CharField(_("tool_type"), max_length=255, blank=True)
    matched_keyword = models.CharField(_("Сработавшее слово"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = _("Лог обогащения")
        verbose_name_plural = _("Логи обогащения")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["result", "tool_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_external_id} → {self.get_result_display()}"


class ModerationProduct(Product):
    """Proxy для очереди модерации обогащения в admin."""

    class Meta:
        proxy = True
        verbose_name = _("Товар на модерации")
        verbose_name_plural = _("Очередь модерации обогащения")


# #517: ProductAvailabilitySubscription вынесена в отдельный модуль (прецедент —
# apps.accounts.wishlist, #329). Импортируем здесь, чтобы модель регистрировалась
# при загрузке app (иначе reverse-аксессор product.availability_subscriptions и
# makemigrations «не видят» модель до первого lazy-импорта).
from apps.catalog import availability_subscriptions as _availability_subscriptions  # noqa: E402

ProductAvailabilitySubscription = _availability_subscriptions.ProductAvailabilitySubscription
# ---------------------------------------------------------------------------
# Catalog processing: audit/apply foundation
# ---------------------------------------------------------------------------


class CatalogProcessingRunKind(models.TextChoices):
    MANUAL = "manual", _("Вручную")
    RULES = "rules", _("Правила")
    RESEARCH = "research", _("Исследование")
    AI = "ai", _("AI")
    IMPORT = "import", _("Импорт")


class CatalogProcessingMode(models.TextChoices):
    TOOL_TYPE = "tool_type", _("Тип инструмента")


class CatalogProcessingRunStatus(models.TextChoices):
    DRAFT = "draft", _("Черновик")
    RUNNING = "running", _("В работе")
    COMPLETED = "completed", _("Завершён")
    FAILED = "failed", _("Ошибка")
    CANCELLED = "cancelled", _("Отменён")


class CatalogProcessingItemStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает")
    PROCESSING = "processing", _("В обработке")
    NEEDS_REVIEW = "needs_review", _("Требует проверки")
    COMPLETED = "completed", _("Завершён")
    FAILED = "failed", _("Ошибка")


class CatalogChangeStatus(models.TextChoices):
    PROPOSED = "proposed", _("Предложено")
    APPROVED = "approved", _("Одобрено")
    REJECTED = "rejected", _("Отклонено")
    APPLIED = "applied", _("Применено")
    SKIPPED = "skipped", _("Пропущено")
    CONFLICT = "conflict", _("Конфликт")
    INVALID = "invalid", _("Невалидно")
    FAILED = "failed", _("Ошибка")
    REVERSED = "reversed", _("Отменено")


class CatalogProcessingRun(models.Model):
    """Один логический запуск обработки каталога."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(
        _("Тип запуска"), max_length=16, choices=CatalogProcessingRunKind.choices
    )
    mode = models.CharField(_("Режим"), max_length=16, choices=CatalogProcessingMode.choices)
    status = models.CharField(
        _("Статус"),
        max_length=16,
        choices=CatalogProcessingRunStatus.choices,
        default=CatalogProcessingRunStatus.DRAFT,
        db_index=True,
    )
    idempotency_key = models.CharField(_("Ключ идемпотентности"), max_length=128, unique=True)
    scope = models.JSONField(_("Скоуп"), default=dict, blank=True)
    ruleset_version = models.CharField(_("Версия правил"), max_length=64, blank=True)
    ruleset_hash = models.CharField(_("Хеш правил"), max_length=64, blank=True)
    taxonomy_hash = models.CharField(_("Хеш таксономии"), max_length=64, blank=True)
    stats = models.JSONField(_("Статистика"), default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Инициатор"),
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Завершён"), null=True, blank=True)

    class Meta:
        verbose_name = _("Запуск обработки каталога")
        verbose_name_plural = _("Запуски обработки каталога")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind}/{self.mode} [{self.status}]"


class CatalogProcessingItem(models.Model):
    """Snapshot одного товара внутри запуска обработки каталога."""

    run = models.ForeignKey(
        CatalogProcessingRun,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name=_("Запуск"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Товар"),
    )
    product_ref = models.PositiveBigIntegerField(_("ID товара для аудита"), db_index=True)
    status = models.CharField(
        _("Статус"),
        max_length=16,
        choices=CatalogProcessingItemStatus.choices,
        default=CatalogProcessingItemStatus.PENDING,
        db_index=True,
    )
    input_snapshot = models.JSONField(_("Входной снапшот"), default=dict, blank=True)
    input_hash = models.CharField(_("Хеш входа"), max_length=64)
    baseline_hashes = models.JSONField(_("Базовые хеши"), default=dict, blank=True)
    needed_targets = models.JSONField(_("Целевые поля"), default=list, blank=True)
    error_code = models.CharField(_("Код ошибки"), max_length=32, blank=True)
    error_detail = models.CharField(_("Детали ошибки"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Завершён"), null=True, blank=True)

    class Meta:
        verbose_name = _("Элемент обработки")
        verbose_name_plural = _("Элементы обработки")
        ordering = ["created_at"]
        unique_together = [("run", "product_ref")]

    def __str__(self) -> str:
        return f"Item#{self.product_ref} [{self.status}]"


class CatalogChange(models.Model):
    """Append-only запись предложения и результата изменения каталога."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(
        CatalogProcessingItem,
        on_delete=models.PROTECT,
        related_name="changes",
        verbose_name=_("Элемент"),
    )
    product_ref = models.PositiveBigIntegerField(_("ID товара для аудита"), db_index=True)
    target_kind = models.CharField(_("Тип цели"), max_length=32)
    target_key = models.CharField(_("Ключ цели"), max_length=64, blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=16,
        choices=CatalogChangeStatus.choices,
        default=CatalogChangeStatus.PROPOSED,
        db_index=True,
    )
    idempotency_key = models.CharField(_("Ключ идемпотентности"), max_length=128, unique=True)
    before_value = models.JSONField(_("Старое значение"), default=dict, blank=True)
    proposed_value = models.JSONField(_("Предложенное значение"), default=dict, blank=True)
    after_value = models.JSONField(_("Итоговое значение"), null=True, blank=True)
    baseline_hash = models.CharField(_("Базовый хеш"), max_length=64, blank=True)
    source = models.CharField(_("Источник"), max_length=16, choices=Source.choices)
    confidence = models.SmallIntegerField(
        _("Уверенность"),
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    rule_ref = models.CharField(_("Ссылка на правило"), max_length=64, blank=True)
    ruleset_hash = models.CharField(_("Хеш набора правил"), max_length=64, blank=True)
    reason_code = models.CharField(_("Код причины"), max_length=32, blank=True)
    reason_detail = models.CharField(_("Детали причины"), max_length=255, blank=True)
    comment = models.CharField(_("Комментарий модератора"), max_length=512, blank=True)
    evidence = models.JSONField(_("Доказательства"), default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Проверил"),
    )
    reviewed_at = models.DateTimeField(_("Время проверки"), null=True, blank=True)
    applied_at = models.DateTimeField(_("Время применения"), null=True, blank=True)
    applied_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Применил"),
    )
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Отмена изменения"),
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изменение каталога")
        verbose_name_plural = _("Изменения каталога")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product_ref", "target_kind", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="catalog_change_confidence_range",
                check=models.Q(confidence__gte=0, confidence__lte=100),
            ),
            models.CheckConstraint(
                name="catalog_change_approved_requires_review",
                check=~models.Q(status=CatalogChangeStatus.APPROVED)
                | (models.Q(reviewed_by__isnull=False) & models.Q(reviewed_at__isnull=False)),
            ),
            models.CheckConstraint(
                name="catalog_change_rejected_requires_review",
                check=~models.Q(status=CatalogChangeStatus.REJECTED)
                | (models.Q(reviewed_by__isnull=False) & models.Q(reviewed_at__isnull=False)),
            ),
            models.CheckConstraint(
                name="catalog_change_applied_requires_after_value",
                check=~models.Q(status=CatalogChangeStatus.APPLIED)
                | (models.Q(after_value__isnull=False) & models.Q(applied_at__isnull=False)),
            ),
        ]

    def __str__(self) -> str:
        return f"Change {self.target_kind} [{self.status}]"


class SalesSource(models.TextChoices):
    """Откуда пришёл факт продажи.

    Разделение источников принципиально: заказы сайта пересчитываются из
    ``orders`` при каждом прогоне (идемпотентно), а выгрузка 1С приходит
    порциями и накапливается — стирать её пересчётом сайта нельзя.
    """

    SITE = "site", _("Заказы сайта")
    ONEC = "1c", _("Продажи 1С")


class ProductSalesFact(models.Model):
    """Сколько штук товара продано за один день по одному источнику.

    Сырьё для рейтинга «хитов»: агрегат по дням, а не по документам — на
    витрине важна динамика, а не первичка. Скользящее окно считается по этим
    строкам (см. ``apps.catalog.sales.rebuild_sales_stats``), поэтому «хит»
    всегда можно объяснить конкретными продажами.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="sales_facts",
        verbose_name=_("Товар"),
    )
    source = models.CharField(_("Источник"), max_length=8, choices=SalesSource.choices)
    date = models.DateField(_("Дата продажи"))
    quantity = models.DecimalField(_("Продано"), max_digits=12, decimal_places=3)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = _("Продажи товара за день")
        verbose_name_plural = _("Продажи товаров по дням")
        constraints = [
            # Идемпотентность: повторная выгрузка того же дня перезаписывает
            # количество, а не удваивает его.
            models.UniqueConstraint(
                fields=["product", "source", "date"], name="catalog_salesfact_unique_day"
            ),
            models.CheckConstraint(
                name="catalog_salesfact_quantity_positive", check=models.Q(quantity__gt=0)
            ),
        ]
        indexes = [
            # Основной запрос пересчёта: «все продажи за окно, сгруппировать по товару».
            models.Index(fields=["date", "product"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} · {self.date} · {self.quantity} ({self.source})"


class ProductSalesStat(models.Model):
    """Готовый рейтинг продаж товара за скользящее окно.

    Денормализация ради витрины: сортировать выдачу и рисовать бейдж «Хит»
    по агрегату фактов на лету — это seq scan на каждый запрос. Строка есть
    ТОЛЬКО у товаров с продажами за окно: отсутствие строки означает «не
    продавался», и такой товар в «хиты» не попадёт даже случайно.
    """

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="sales_stat",
        verbose_name=_("Товар"),
    )
    quantity = models.DecimalField(_("Продано за окно"), max_digits=14, decimal_places=3)
    days_with_sales = models.PositiveIntegerField(_("Дней с продажами"), default=0)
    window_days = models.PositiveIntegerField(_("Окно, дней"))
    rank = models.PositiveIntegerField(_("Место в рейтинге"))
    is_hit = models.BooleanField(
        _("Хит продаж"),
        default=False,
        help_text=_("Топ рейтинга при достаточном числе продаж — источник бейджа «Хит»."),
    )
    last_sold_on = models.DateField(_("Последняя продажа"), null=True, blank=True)
    computed_at = models.DateTimeField(_("Пересчитан"), auto_now=True)

    class Meta:
        verbose_name = _("Рейтинг продаж товара")
        verbose_name_plural = _("Рейтинг продаж товаров")
        ordering = ["rank"]
        indexes = [
            models.Index(fields=["-quantity"]),
            models.Index(fields=["is_hit", "rank"]),
        ]

    def __str__(self) -> str:
        return f"#{self.rank} · {self.product_id} · {self.quantity}"
