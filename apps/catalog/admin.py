from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from apps.core.events import EventSource, product_created, product_updated
from apps.pricing.models import PriceRecord
from apps.pricing.services import WHOLESALE, price_for

from .availability_subscriptions import ProductAvailabilitySubscription
from .models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogProcessingItem,
    CatalogProcessingRun,
    Category,
    CategoryAttribute,
    CategoryMappingRule,
    EnrichmentLog,
    GroupCategoryMapping,
    ImportRun,
    OneCGroup,
    Product,
    ProductAttributeValue,
    ProductCompatibility,
    ProductImage,
    ProductStatus,
    SiteCategory,
    Source,
)
from . import processing
from .read_models import rebuild_attrs_cache


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 2
    prepopulated_fields = {"slug": ("value",)}


class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 1
    autocomplete_fields = ["attribute"]
    fields = ("attribute", "is_filter", "group", "is_seo_facet", "is_required", "sort_order")


class CategoryAdminForm(movenodeform_factory(Category)):
    """Форма дерева категорий с подсказкой о независимости от 1С.

    Дерево категорий — мастер структуры сайта (ведётся ЗДЕСЬ). Связь с 1С
    (`external_id_1c`) — справочная: переразбор/импорт 1С не меняет дерево и не
    перетирает ручные категории товаров (`category_is_manual`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "external_id_1c" in self.fields:
            self.fields["external_id_1c"].help_text = _(
                "Справочный код группы 1С. Дерево категорий ведётся здесь, в админке "
                "(сайт — мастер структуры). Импорт/переразбор 1С НЕ меняет это дерево и "
                "не перетирает ручные категории товаров."
            )


@admin.register(Category)
class CategoryAdmin(TreeAdmin):
    form = CategoryAdminForm
    # Крупный заголовок с именем редактируемой категории (вместо общего «Категории»).
    change_form_template = "admin/catalog/category/change_form.html"
    list_display = (
        "name",
        "slug",
        "external_id_1c",
        "products_count",
        "published_count",
        "on_site",
        "is_active",
        "sort_order",
    )
    list_filter = ("on_site", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug", "external_id_1c")
    inlines = [CategoryAttributeInline]
    readonly_fields = ("products_total",)
    actions = [
        "action_show_on_site",
        "action_hide_from_site",
        "action_activate",
        "action_deactivate",
    ]

    @staticmethod
    def _subtree_count_sq(*, published=False):
        """Подзапрос: число товаров во ВСЁМ поддереве категории (узел + потомки).

        Дерево treebeard MP_Node: потомки имеют path с префиксом path узла, поэтому
        ``category__path__startswith=path`` накрывает узел и всех потомков. Скаляр-агрегат
        по КОНСТАНТНОЙ строковой группе (Value("x")) — одна строка-счётчик; строку (не int)
        берём нарочно, чтобы PostgreSQL не принял ``GROUP BY <int>`` за номер колонки. На
        PostgreSQL лукап startswith по выражению (OuterRef) даёт ``LIKE outer.path || '%'`` —
        корректный префикс (пути treebeard без LIKE-метасимволов)."""
        qs = Product.objects.filter(category__path__startswith=OuterRef("path"))
        if published:
            qs = qs.filter(status=ProductStatus.PUBLISHED)
        return Coalesce(
            Subquery(
                qs.order_by()
                .annotate(_g=Value("x"))
                .values("_g")
                .annotate(c=Count("pk"))
                .values("c"),
                output_field=IntegerField(),
            ),
            0,
        )

    def get_queryset(self, request):
        # «Товаров»/«Опубл.» считаем по ВСЕМУ поддереву (включая родительские узлы, у
        # которых нет прямых товаров — они лежат в листьях). Подзапросом на узел, без N+1.
        return (
            super()
            .get_queryset(request)
            .annotate(
                _products=self._subtree_count_sq(),
                _published=self._subtree_count_sq(published=True),
            )
        )

    @staticmethod
    def _product_count_link(path, count, *, status=None):
        """Счётчик-ссылка в список товаров админки по ВСЕМУ поддереву категории
        (``category__path__startswith=<path>`` — узел + потомки, число и страница
        совпадают). 0 — без ссылки."""
        if not count:
            return count
        url = f"{reverse('admin:catalog_product_changelist')}?category__path__startswith={path}"
        if status:
            url += f"&status={status}"
        return format_html('<a href="{}">{}</a>', url, count)

    @admin.display(description=_("Товаров"), ordering="_products")
    def products_count(self, obj):
        return self._product_count_link(obj.path, getattr(obj, "_products", 0))

    @admin.display(description=_("Опубл."), ordering="_published")
    def published_count(self, obj):
        return self._product_count_link(
            obj.path, getattr(obj, "_published", 0), status=ProductStatus.PUBLISHED.value
        )

    @admin.display(description=_("Товаров в категории"))
    def products_total(self, obj):
        """Счётчик товаров на странице правки категории (со ссылкой-drill-down в список
        товаров) — по всему поддереву. Аннотация _products доступна и на форме
        (admin.get_object → get_queryset); fallback на запрос — на случай отсутствия
        аннотации. На добавлении — прочерк."""
        if obj is None or not obj.pk:
            return "—"
        count = getattr(obj, "_products", None)
        if count is None:
            count = Product.objects.filter(category__path__startswith=obj.path).count()
        return self._product_count_link(obj.path, count)

    @admin.action(description=_("Показать на сайте"))
    def action_show_on_site(self, request, queryset):
        n = queryset.update(on_site=True)
        self.message_user(request, _("Показано на сайте: %d") % n)

    @admin.action(description=_("Скрыть с сайта"))
    def action_hide_from_site(self, request, queryset):
        n = queryset.update(on_site=False)
        self.message_user(request, _("Скрыто с сайта: %d") % n)

    @admin.action(description=_("Активировать"))
    def action_activate(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, _("Активировано: %d") % n)

    @admin.action(description=_("Деактивировать"))
    def action_deactivate(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, _("Деактивировано: %d") % n)


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "attribute_type",
        "unit",
        "is_filterable",
        "is_ai_feature",
        "values_count",
        "options_count",
        "used_in_categories",
    )
    list_filter = ("attribute_type", "is_filterable", "is_ai_feature")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [AttributeOptionInline]

    def get_queryset(self, request):
        # Счётчики — коррелированными подзапросами, а НЕ двумя Count(distinct=True) в одном
        # annotate: две агрегатные JOIN-связи (PAV и options) в одном запросе дают декартово
        # произведение, и COUNT(DISTINCT) считается по миллионам строк — страница висела секунды.
        # Подзапрос на каждую связь убирает фан-аут (FK attribute_id проиндексирован).
        # related_name: PAV.attribute не задан → "productattributevalue"; варианты → "options".
        pav_count = (
            ProductAttributeValue.objects.filter(attribute=OuterRef("pk"))
            .values("attribute")
            .annotate(c=Count("id"))
            .values("c")
        )
        opt_count = (
            AttributeOption.objects.filter(attribute=OuterRef("pk"))
            .values("attribute")
            .annotate(c=Count("id"))
            .values("c")
        )
        return (
            super()
            .get_queryset(request)
            .annotate(
                _values_count=Coalesce(Subquery(pav_count, output_field=IntegerField()), 0),
                _options_count=Coalesce(Subquery(opt_count, output_field=IntegerField()), 0),
            )
            .prefetch_related("category_attributes__category")
        )

    @admin.display(description=_("Значений"), ordering="_values_count")
    def values_count(self, obj):
        return obj._values_count

    @admin.display(description=_("Вариантов"), ordering="_options_count")
    def options_count(self, obj):
        return obj._options_count

    @admin.display(description=_("Категории"))
    def used_in_categories(self, obj):
        names = [ca.category.name for ca in obj.category_attributes.all()]
        if not names:
            return "—"
        head = ", ".join(names[:5])
        return head if len(names) <= 5 else f"{head} … (+{len(names) - 5})"


class ConfidenceFilter(admin.SimpleListFilter):
    """Быстрый фильтр уверенности значения — найти ненадёжное извлечение."""

    title = _("Уверенность")
    parameter_name = "confidence_band"

    def lookups(self, request, model_admin):
        return [("high", _("100 (точно)")), ("mid", _("90–99")), ("low", _("ниже 90"))]

    def queryset(self, request, queryset):
        if self.value() == "high":
            return queryset.filter(confidence=100)
        if self.value() == "mid":
            return queryset.filter(confidence__gte=90, confidence__lt=100)
        if self.value() == "low":
            return queryset.filter(confidence__lt=90)
        return queryset


@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    """Все извлечённые значения характеристик — ревью результатов enrich.

    Бизнес-правило: ручная правка значения здесь = подтверждение человеком →
    source=manual, confidence=100 (защита от перезаписи enrich_attributes).
    """

    # Поля значения PAV: их ручная правка переводит запись в source=manual.
    VALUE_FIELDS = ("value_text", "value_integer", "value_decimal", "value_boolean", "value_option")

    list_display = ("product", "attribute", "display_value", "source", "confidence")
    list_filter = ("attribute", "source", "attribute__attribute_type", ConfidenceFilter)
    search_fields = ("product__name", "product__article", "product__code_1c", "value_text")
    list_select_related = ("product", "attribute", "value_option")
    autocomplete_fields = ("product", "attribute")
    raw_id_fields = ("value_option",)
    # source/confidence меняются только автоматически (см. save_model), руками — нельзя.
    readonly_fields = ("source", "confidence")

    @admin.display(description=_("Значение"))
    def display_value(self, obj):
        t = obj.attribute.attribute_type
        if t in (AttributeType.SELECT, AttributeType.MULTISELECT):
            return obj.value_option.value if obj.value_option_id else "—"
        if t == AttributeType.BOOLEAN:
            if obj.value_boolean is None:
                return "—"
            return _("Да") if obj.value_boolean else _("Нет")
        if t == AttributeType.DECIMAL:
            if obj.value_decimal is None:
                return "—"
            return f"{obj.value_decimal} {obj.attribute.unit}".strip()
        if t == AttributeType.INTEGER:
            if obj.value_integer is None:
                return "—"
            return f"{obj.value_integer} {obj.attribute.unit}".strip()
        return obj.value_text or "—"

    def save_model(self, request, obj, form, change):
        # Любое ручное изменение значения = подтверждение человеком (authoritative).
        if any(f in form.changed_data for f in self.VALUE_FIELDS):
            obj.source = Source.MANUAL
            obj.confidence = 100
        super().save_model(request, obj, form, change)


@admin.register(CategoryMappingRule)
class CategoryMappingRuleAdmin(admin.ModelAdmin):
    list_display = (
        "priority",
        "rule_type",
        "pattern",
        "exclude_pattern",
        "target_category",
        "is_active",
    )
    list_filter = ("rule_type", "is_active", "target_category")
    search_fields = ("pattern", "exclude_pattern", "brand", "note")
    list_editable = ("is_active",)
    autocomplete_fields = ["target_category"]
    ordering = ("priority", "id")
    fieldsets = (
        (
            None,
            {
                "description": _(
                    "Слой маршрутизации «группа/признак 1С → категория сайта». Правила "
                    "влияют только на авторазбор НОВЫХ и ещё не размеченных вручную "
                    "товаров: товар с ручной категорией (category_is_manual) правила НЕ "
                    "трогают. Само дерево категорий правила не меняют — оно ведётся в "
                    "разделе «Категории»."
                ),
                "fields": (
                    "rule_type",
                    "pattern",
                    "exclude_pattern",
                    "brand",
                    "target_category",
                    "priority",
                    "is_active",
                    "note",
                ),
            },
        ),
    )


class UncategorizedFilter(admin.SimpleListFilter):
    """Фильтр «Неразобранные» — товары без категории сайта."""

    title = _("Разбор по категориям")
    parameter_name = "categorized"

    def lookups(self, request, model_admin):
        return [("no", _("Неразобранные")), ("yes", _("С категорией"))]

    def queryset(self, request, queryset):
        if self.value() == "no":
            return queryset.filter(category__isnull=True)
        if self.value() == "yes":
            return queryset.filter(category__isnull=False)
        return queryset


class ModerationQueueFilter(admin.SimpleListFilter):
    """Очередь модерации каталога (#51).

    Все три значения — чистый SQL по полям (status/category), без вызова
    publication_errors() построчно (иначе фильтрация тяжёлая на больших выборках).
    Точную причину (нехватку обязательных характеристик) показывает колонка
    `moderation_reason`, а не этот фильтр.
    """

    title = _("Очередь модерации")
    parameter_name = "moderation"

    def lookups(self, request, model_admin):
        return [
            ("attention", _("Требуют внимания")),
            ("needs_review", _("Требуют проверки")),
            ("imported", _("Импортированы (не разобраны)")),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "needs_review":
            return queryset.filter(status=ProductStatus.NEEDS_REVIEW)
        if value == "imported":
            return queryset.filter(status=ProductStatus.IMPORTED)
        if value == "attention":
            # Не опубликован И (без категории ИЛИ статус imported/needs_review).
            # Точную нехватку обязательных характеристик на уровне SQL не ловим —
            # её видно в колонке moderation_reason.
            return queryset.exclude(status=ProductStatus.PUBLISHED).filter(
                Q(category__isnull=True)
                | Q(status__in=[ProductStatus.IMPORTED, ProductStatus.NEEDS_REVIEW])
            )
        return queryset


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    autocomplete_fields = ["attribute"]
    fields = (
        "attribute",
        "value_text",
        "value_integer",
        "value_decimal",
        "value_boolean",
        "value_option",
        "source",
        "confidence",
    )


class CurrentPriceInline(admin.TabularInline):
    """Текущие цены товара из 1С по типам (retail/wholesale) — только просмотр.

    Цены ведёт 1С (ADR-0006), поэтому инлайн read-only: менеджер видит обе цены
    в карточке, но не редактирует их здесь.
    """

    model = PriceRecord
    fk_name = "product"
    extra = 0
    can_delete = False
    verbose_name = _("Цена 1С (текущая)")
    verbose_name_plural = _("Цены 1С (текущие, по типам)")
    fields = ("price_type", "value", "currency", "is_current", "valid_from")
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_current=True)

    def has_add_permission(self, request, obj=None):
        return False


class ProductCompatibilityInline(admin.TabularInline):
    """Исходящие связи совместимости (товар = source): аксессуары и «совместим с»."""

    model = ProductCompatibility
    fk_name = "source"
    extra = 1
    autocomplete_fields = ["target"]
    fields = ("target", "kind", "note", "sort_order")
    verbose_name = _("Связь совместимости (исходящая)")
    verbose_name_plural = _("Связи совместимости (исходящие)")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("target")


class ProductCompatibilityIncomingInline(admin.TabularInline):
    """Входящие связи (товар = target) — только просмотр: «к чему подходит / с чем совместим»."""

    model = ProductCompatibility
    fk_name = "target"
    extra = 0
    fields = ("source", "kind", "note", "sort_order")
    readonly_fields = ("source", "kind", "note", "sort_order")
    verbose_name = _("Связь совместимости (входящая)")
    verbose_name_plural = _("Связи совместимости (входящие, только просмотр)")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProductActionForm(ActionForm):
    """Action-форма списка товаров с выбором целевой категории для bulk-перепривязки."""

    target_category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        label=_("Категория для перепривязки"),
        help_text=_("Используется действием «Перепривязать…»."),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    action_form = ProductActionForm
    list_display = (
        "name",
        "article",
        "brand",
        "category",
        "status",
        "moderation_reason",
        "stock_status",
        "price",
        "current_wholesale",
        "is_active",
    )
    list_filter = (
        "status",
        ModerationQueueFilter,
        UncategorizedFilter,
        "stock_status",
        "is_active",
        "brand",
    )
    search_fields = ("name", "original_name", "article", "code_1c", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["category"]
    list_select_related = ("category",)

    def lookup_allowed(self, lookup, value, request=None):
        # Drill-down из списка категорий: ссылка по поддереву (?category__path__startswith=<path>)
        # или по точному узлу (?category__id__exact=<id>). Категорию НЕ кладём в list_filter
        # (дропдаун всех узлов дерева был бы тяжёлым) — точечно разрешаем эти лукапы.
        if lookup in ("category__id__exact", "category__path__startswith"):
            return True
        return super().lookup_allowed(lookup, value, request)

    readonly_fields = (
        "moderation_reason_detail",
        "code_1c",
        "original_name",
        "source_group",
        "matched_rule",
        "pricing_summary",
        "price_updated_at",
        "stock_updated_at",
        "attrs_cache",
        "created_at",
        "updated_at",
    )
    actions = [
        "action_set_category",
        "action_publish",
        "action_needs_review",
        "action_rebuild_attrs_cache",
    ]
    fieldsets = (
        (
            None,
            {"fields": ("moderation_reason_detail", "name", "slug", "status", "is_active")},
        ),
        (
            _("Категория сайта"),
            {
                "description": _(
                    "Категория ведётся на сайте (1С её не диктует). Ручное назначение "
                    "включает «Категория задана вручную» — после этого импорт/авторазбор "
                    "1С её НЕ меняет. Массовая перепривязка — действием «Перепривязать "
                    "выбранные товары…» в списке товаров."
                ),
                "fields": ("category", "category_is_manual", "matched_rule"),
            },
        ),
        (
            _("Данные из 1С"),
            {
                "fields": (
                    "code_1c",
                    "article",
                    "barcode",
                    "original_name",
                    "source_group",
                    "unit",
                    "is_active_1c",
                )
            },
        ),
        (_("Бренд и контент"), {"fields": ("brand", "short_description", "description")}),
        (
            _("Цена и наличие"),
            {
                "description": _(
                    "«Цена» — кэш розницы из 1С (источник истины — 1С, ручная правка "
                    "перезатрётся при следующей синхронизации). Что увидит покупатель — "
                    "ниже в «Расчёт цены»; опт ведётся в «Цены 1С (текущие)»."
                ),
                "fields": (
                    "pricing_summary",
                    "price",
                    "old_price",
                    "currency",
                    "stock_quantity",
                    "reserved_quantity",
                    "available_quantity",
                    "stock_status",
                    "price_updated_at",
                    "stock_updated_at",
                ),
            },
        ),
        (_("SEO"), {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
        (
            _("Служебное"),
            {"fields": ("attrs_cache", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    inlines = [
        ProductImageInline,
        ProductAttributeValueInline,
        CurrentPriceInline,
        ProductCompatibilityInline,
        ProductCompatibilityIncomingInline,
    ]

    def get_queryset(self, request):
        # Сброс кэша required-атрибутов на КАЖДЫЙ рендер списка: ProductAdmin —
        # синглтон на процесс, без сброса карта category_id -> [CategoryAttribute]
        # пережила бы запрос и колонка moderation_reason показывала бы устаревшую
        # причину после правки обязательных атрибутов категории. get_queryset
        # вызывается раз на отрисовку changelist → кэш становится request-scoped.
        self._req_attrs_cache = {}
        # Текущая оптовая цена — подзапросом, чтобы колонка списка не делала N+1.
        wholesale = PriceRecord.objects.filter(
            product=OuterRef("pk"), price_type=WHOLESALE, is_current=True
        ).values("value")[:1]
        # select_related("category") + prefetch значений характеристик: чтобы
        # колонка moderation_reason (publication_errors / missing_required_attributes)
        # не плодила N+1 на категории и на attribute_values.
        return (
            super()
            .get_queryset(request)
            .annotate(_wholesale_price=Subquery(wholesale))
            .select_related("category")
            .prefetch_related("attribute_values__attribute")
        )

    # Решение по N+1 в колонке moderation_reason:
    # missing_required_attributes() на каждый товар делает запрос к
    # CategoryAttribute. Чтобы это не давало N+1 по числу ТОВАРОВ, держим на
    # инстансе admin (живёт в рамках одного рендера changelist) карту
    # category_id -> [required CategoryAttribute] с ленивой дозагрузкой по
    # КАТЕГОРИЯМ: первая встреча незнакомой категории добирает её required-атрибуты
    # одним запросом и кэширует. Итог: число запросов = число УНИКАЛЬНЫХ категорий
    # на странице (десятки в худшем случае), а не число товаров. attribute_values
    # берутся из prefetch (см. get_queryset), категория — из select_related.
    def _required_attrs_for_category(self, category_id):
        cache = getattr(self, "_req_attrs_cache", None)
        if cache is None:
            cache = {}
            self._req_attrs_cache = cache
        if category_id not in cache:
            cache[category_id] = list(
                CategoryAttribute.objects.filter(
                    category_id=category_id, is_required=True
                ).select_related("attribute")
            )
        return cache[category_id]

    @admin.display(description=_("Причина в очереди"))
    def moderation_reason(self, obj):
        """Краткая причина, почему товар не публикуется (вычисляется на лету).

        Опубликованный товар → «—». Иначе — короткий текст: «Нет категории»
        и/или «Не хватает: …». Без N+1: категория из select_related, значения из
        prefetch (get_queryset), required-атрибуты — из кэша по категориям.
        """
        if obj.status == ProductStatus.PUBLISHED:
            return "—"

        parts: list[str] = []
        if not obj.category_id:
            parts.append("Нет категории")
        else:
            required = self._required_attrs_for_category(obj.category_id)
            if required:
                from .read_models import attr_value_to_json

                filled = set()
                for pav in obj.attribute_values.all():
                    value = attr_value_to_json(pav)
                    if value is not None and value != "":
                        filled.add(pav.attribute_id)
                missing = [ca.attribute.name for ca in required if ca.attribute_id not in filled]
                if missing:
                    parts.append("Не хватает: " + ", ".join(missing))
        return "; ".join(parts) if parts else "—"

    @admin.display(description=_("Причина непубликации"))
    def moderation_reason_detail(self, obj):
        """Полный список ошибок публикации построчно — для карточки товара.

        Использует единый источник правил publication_errors(). На форме одного
        товара N+1 неважен (одна запись).
        """
        if obj is None or obj.pk is None:
            return "—"
        errors = obj.publication_errors()
        if not errors:
            return "—" if obj.status == ProductStatus.PUBLISHED else "Готов к публикации"
        # Построчно через <br>; каждая строка экранируется (format_html).
        return format_html_join(mark_safe("<br>"), "• {}", ((e,) for e in errors))

    @admin.display(description=_("Опт"))
    def current_wholesale(self, obj):
        value = getattr(obj, "_wholesale_price", None)
        return value if value is not None else "—"

    @admin.display(description=_("Расчёт цены (price_for)"))
    def pricing_summary(self, obj):
        """Что увидит покупатель: розница (аноним) и опт (B2B). Через единый price_for."""
        if obj.pk is None:
            return "—"
        retail = price_for(obj)  # без user → розница
        retail_str = f"{retail.final} {retail.currency}" if retail.has_price else "—"
        wholesale = (
            obj.price_records.filter(price_type=WHOLESALE, is_current=True)
            .values_list("value", flat=True)
            .first()
        )
        wholesale_str = f"{wholesale} {obj.currency or 'RUB'}" if wholesale is not None else "—"
        return f"розница: {retail_str}  ·  опт (B2B): {wholesale_str}"

    def save_model(self, request, obj, form, change):
        # Менеджер вручную задал категорию → фиксируем, чтобы авторазбор её не трогал.
        if "category" in form.changed_data and obj.category_id is not None:
            obj.category_is_manual = True
        super().save_model(request, obj, form, change)

        # Доменное событие — из admin-flow, после коммита; в payload только id.
        if change:
            changed_fields = list(form.changed_data)
            if changed_fields:
                transaction.on_commit(
                    lambda pid=obj.pk, c=changed_fields: product_updated.send(
                        sender=Product, product_id=pid, source=EventSource.ADMIN, changed_fields=c
                    )
                )
        else:
            transaction.on_commit(
                lambda pid=obj.pk: product_created.send(
                    sender=Product, product_id=pid, source=EventSource.ADMIN
                )
            )

    def save_related(self, request, form, formsets, change):
        # Инлайны (в т.ч. значения характеристик) сохраняются здесь — проверку
        # публикации делаем ПОСЛЕ них, когда PAV уже в БД. clean() на форме ловит
        # существующий товар до сохранения, но для нового товара порядок сохранения
        # инлайнов не позволяет валидировать в clean — поэтому здесь safe-fallback:
        # не публикуем, а откатываем в «Требует проверки» (без исключения).
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.status == ProductStatus.PUBLISHED and obj.publication_errors():
            obj.status = ProductStatus.NEEDS_REVIEW
            obj.is_active = False
            obj.save(update_fields=["status", "is_active", "updated_at"])
            self.message_user(
                request,
                "Не опубликовано: " + "; ".join(obj.publication_errors()),
                level=messages.ERROR,
            )

    @staticmethod
    def _emit_bulk_updated(ids: list[int], changed_fields: list[str]) -> None:
        """Эмит product_updated по каждому реально изменённому товару (после коммита)."""

        def _send():
            for pid in ids:
                product_updated.send(
                    sender=Product,
                    product_id=pid,
                    source=EventSource.ADMIN,
                    changed_fields=changed_fields,
                )

        transaction.on_commit(_send)

    @admin.action(description=_("Перепривязать выбранные товары в категорию (поле справа)"))
    def action_set_category(self, request, queryset):
        # Bulk-перепривязка в категорию из поля action-формы. Фиксируем
        # category_is_manual=True — это и есть защита: дальнейший авторазбор/импорт
        # 1С эти товары не перевесит. Категория не влияет на attrs_cache, поэтому
        # update() безопасен; событие эмитим по реально затронутым.
        cat_id = request.POST.get("target_category")
        if not cat_id:
            self.message_user(
                request,
                _("Выберите категорию в поле «Категория для перепривязки» рядом с действием."),
                level=messages.WARNING,
            )
            return
        category = Category.objects.filter(is_active=True, pk=cat_id).first()
        if category is None:
            self.message_user(
                request,
                _("Категория не найдена или неактивна."),
                level=messages.ERROR,
            )
            return
        # Меняем ТОЛЬКО товары с другой категорией (паттерн action_publish): чтобы
        # не слать ложные product_updated и не переводить в «ручной» режим товары,
        # которые и так уже в этой категории. Категория не влияет на attrs_cache —
        # update() безопасен.
        changed = queryset.exclude(category=category)
        ids = list(changed.values_list("id", flat=True))
        updated = changed.update(category=category, category_is_manual=True)
        skipped = queryset.count() - updated
        if ids:
            self._emit_bulk_updated(ids, ["category"])
        self.message_user(
            request,
            _(
                "Перепривязано в «%(cat)s»: %(n)d (уже были в категории: %(s)d). "
                "Зафиксировано как ручное — переразбор/импорт 1С эти товары не изменит."
            )
            % {"cat": category.name, "n": updated, "s": skipped},
        )

    @admin.action(description=_("Опубликовать выбранные товары"))
    def action_publish(self, request, queryset):
        # НЕ обходим валидацию через queryset.update(): для каждого товара
        # проверяем publication_errors() (категория + обязательные характеристики).
        # Невалидные пропускаем; событие эмитим только по реально опубликованным.
        # Уже опубликованные и активные — no-op: не трогаем (без лишних событий).
        qs = (
            queryset.exclude(status=ProductStatus.PUBLISHED, is_active=True)
            .select_related("category")
            .prefetch_related("attribute_values__attribute", "attribute_values__value_option")
        )
        ok_ids: list[int] = []
        skipped = 0
        for p in qs:
            if p.publication_errors():
                skipped += 1
            else:
                ok_ids.append(p.id)
        Product.objects.filter(id__in=ok_ids).update(status=ProductStatus.PUBLISHED, is_active=True)
        if ok_ids:
            self._emit_bulk_updated(ok_ids, ["status", "is_active"])
        self.message_user(
            request,
            f"Опубликовано: {len(ok_ids)}, пропущено: {skipped} — "
            "не хватает обязательных характеристик/категории",
        )

    @admin.action(description=_("Пересобрать attrs_cache"))
    def action_rebuild_attrs_cache(self, request, queryset):
        # Пересборка денормализованного кэша характеристик из EAV — без
        # save_model и доменных событий (это служебная операция, не правка контента).
        for product in queryset:
            rebuild_attrs_cache(product)
        self.message_user(request, f"Пересобрано: {queryset.count()}")

    @admin.action(description=_("Вернуть на проверку"))
    def action_needs_review(self, request, queryset):
        qs = queryset.exclude(status=ProductStatus.NEEDS_REVIEW)
        ids = list(qs.values_list("id", flat=True))
        updated = qs.update(status=ProductStatus.NEEDS_REVIEW)
        if ids:
            self._emit_bulk_updated(ids, ["status"])
        self.message_user(request, _("Отправлено на проверку: %d") % updated)


# ---------------------------------------------------------------------------
# Журналы загрузки и обогащения каталога
# ---------------------------------------------------------------------------


def _stat(key, short):
    """Колонка list_display, читающая счётчик из ImportRun.stats (JSONB)."""

    @admin.display(description=short)
    def getter(self, obj):
        return (obj.stats or {}).get(key, "—")

    getter.__name__ = f"stat_{key}"
    return getter


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "status",
        "started_at",
        "finished_at",
        "stat_categories_created",
        "stat_products_imported",
        "stat_tool_type_assigned",
        "stat_moderation",
        "stat_recategorize_flagged",
        "stat_excluded",
    )
    list_filter = ("status", "source")
    ordering = ("-started_at",)
    readonly_fields = ("started_at", "finished_at", "source", "status", "stats")

    stat_categories_created = _stat("categories_created", _("Категорий"))
    stat_products_imported = _stat("products_imported", _("Товаров"))
    stat_tool_type_assigned = _stat("tool_type_assigned", _("tool_type"))
    stat_moderation = _stat("moderation", _("Модерация"))
    stat_recategorize_flagged = _stat("recategorize_flagged", _("Recategorize"))
    stat_excluded = _stat("excluded", _("Исключено"))

    def has_add_permission(self, request):
        return False


@admin.register(EnrichmentLog)
class EnrichmentLogAdmin(admin.ModelAdmin):
    list_display = (
        "product_external_id",
        "raw_name",
        "category_path",
        "result",
        "tool_type",
        "matched_keyword",
    )
    list_filter = ("result", "tool_type", "run")
    search_fields = ("raw_name", "product_external_id")
    list_select_related = ("run",)
    readonly_fields = (
        "run",
        "product_external_id",
        "raw_name",
        "category_path",
        "result",
        "tool_type",
        "matched_keyword",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OneCGroup)
class OneCGroupAdmin(admin.ModelAdmin):
    """Реестр групп номенклатуры 1С (синкается catalog_sync_1c_groups; правится обменом).

    Иерархия 1С: колонка «Родитель» + отступ в имени по глубине вложенности.
    """

    list_display = (
        "indented_name",
        "code",
        "status",
        "product_count",
        "mapped_category",
    )
    list_filter = ("status",)
    search_fields = ("name", "code")
    autocomplete_fields = ["mapped_category", "parent"]
    readonly_fields = ("product_count", "updated_at")
    # Сортировка по материализованному пути → дети идут сразу под родителем (pre-order,
    # как дерево «Категории»). Заполняется синком (tree_path).
    ordering = ("tree_path", "name")
    list_select_related = ("parent", "mapped_category")

    def has_add_permission(self, request):
        # Группы заводятся синком из 1С/маппинга, не вручную.
        return False

    @admin.display(description=_("Группа 1С (дерево)"), ordering="tree_path")
    def indented_name(self, obj):
        # Глубина = число разделителей в материализованном пути (быстро, без запросов).
        from apps.catalog.models import ONEC_TREE_SEP

        depth = (obj.tree_path or "").count(ONEC_TREE_SEP)
        prefix = format_html("".join(["&nbsp;&nbsp;&nbsp;&nbsp;"] * depth))
        return format_html("{}{}{}", prefix, "└ " if depth else "", obj.name)


@admin.register(GroupCategoryMapping)
class GroupCategoryMappingAdmin(admin.ModelAdmin):
    """Сопоставление «группа 1С → категория сайта» + действие «применить к товарам»."""

    list_display = ("name", "code", "status", "product_count", "mapped_category")
    list_filter = ("status",)
    search_fields = ("name", "code")
    autocomplete_fields = ["mapped_category"]
    readonly_fields = ("name", "code", "site_path", "product_count", "status", "updated_at")
    ordering = ("-product_count", "name")
    actions = ["action_apply"]

    def has_add_permission(self, request):
        return False

    @admin.action(description=_("Применить: расставить товары групп в их категории"))
    def action_apply(self, request, queryset):
        from .onec_groups import apply_group_mapping

        moved = skipped = 0
        for group in queryset:
            if not group.mapped_category_id:
                skipped += 1
                continue
            moved += apply_group_mapping(group)
        self.message_user(
            request,
            _("Перенесено товаров: %(m)d. Групп без категории пропущено: %(s)d.")
            % {"m": moved, "s": skipped},
            level=messages.SUCCESS if moved else messages.WARNING,
        )


@admin.register(SiteCategory)
class SiteCategoryAdmin(CategoryAdmin):
    """«Категории (сайт)» — только курируемое v2-дерево (узлы is_site_v2=True).

    Признак is_site_v2 ставят build_skeleton/build_section; легаси-зеркала групп 1С
    его не имеют, поэтому не попадают сюда (даже при совпадении slug).
    """

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_site_v2=True)


@admin.register(ProductAvailabilitySubscription)
class ProductAvailabilitySubscriptionAdmin(admin.ModelAdmin):
    """Read-only — жизненный цикл ведёт apps.catalog.availability_subscriptions,
    не ручное редактирование (как NotificationLog/Notification, #514/#515)."""

    list_display = ("user", "product", "channel", "status", "subscribed_at", "notified_at")
    list_filter = ("channel", "status")
    search_fields = ("user__phone", "product__name", "product__article")
    readonly_fields = (
        "user",
        "product",
        "channel",
        "status",
        "subscribed_at",
        "queued_at",
        "notified_at",
        "cancelled_at",
    )
    date_hierarchy = "subscribed_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Catalog processing audit admin
# ---------------------------------------------------------------------------


class CatalogProcessingItemInline(admin.TabularInline):
    model = CatalogProcessingItem
    extra = 0
    readonly_fields = (
        "product",
        "product_ref",
        "status",
        "input_hash",
        "baseline_hashes",
        "needed_targets",
        "error_code",
        "error_detail",
        "created_at",
        "finished_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CatalogProcessingRun)
class CatalogProcessingRunAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "mode", "status", "idempotency_key", "created_at", "finished_at")
    list_filter = ("kind", "mode", "status")
    search_fields = ("idempotency_key",)
    readonly_fields = (
        "id",
        "kind",
        "mode",
        "status",
        "idempotency_key",
        "scope",
        "ruleset_version",
        "ruleset_hash",
        "taxonomy_hash",
        "stats",
        "created_by",
        "created_at",
        "finished_at",
    )
    inlines = [CatalogProcessingItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogProcessingItem)
class CatalogProcessingItemAdmin(admin.ModelAdmin):
    list_display = ("run", "product_ref", "status", "input_hash", "created_at", "finished_at")
    list_filter = ("status", "run__kind", "run__mode")
    search_fields = ("product_ref", "run__idempotency_key")
    readonly_fields = (
        "run",
        "product",
        "product_ref",
        "status",
        "input_snapshot",
        "input_hash",
        "baseline_hashes",
        "needed_targets",
        "error_code",
        "error_detail",
        "created_at",
        "finished_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogChange)
class CatalogChangeAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "target_kind",
        "status",
        "source",
        "confidence",
        "reason_code",
        "created_at",
        "applied_at",
    )
    list_filter = ("status", "source", "target_kind")
    search_fields = ("idempotency_key", "product_ref")
    readonly_fields = (
        "id",
        "item",
        "product_ref",
        "target_kind",
        "target_key",
        "status",
        "idempotency_key",
        "before_value",
        "proposed_value",
        "after_value",
        "baseline_hash",
        "source",
        "confidence",
        "rule_ref",
        "ruleset_hash",
        "reason_code",
        "reason_detail",
        "evidence",
        "reviewed_by",
        "reviewed_at",
        "applied_at",
        "reversal_of",
        "created_at",
    )
    actions = ["approve_changes", "reject_changes", "apply_changes"]

    @admin.action(description=_("Одобрить выбранные предложения"))
    def approve_changes(self, request, queryset):
        if not settings.FEATURES.get("catalog_processing", False):
            self.message_user(request, "Feature catalog_processing выключен", messages.ERROR)
            return
        reviewer_id = request.user.pk if request.user.is_authenticated else None
        if not reviewer_id:
            self.message_user(request, "Не удалось определить модератора", messages.ERROR)
            return
        count = 0
        for change in queryset.filter(status="proposed"):
            result = processing.review_catalog_change(change.pk, "approved", reviewer_id)
            if result.status == "approved":
                count += 1
        self.message_user(request, f"Одобрено: {count}", messages.SUCCESS)

    @admin.action(description=_("Отклонить выбранные предложения"))
    def reject_changes(self, request, queryset):
        if not settings.FEATURES.get("catalog_processing", False):
            self.message_user(request, "Feature catalog_processing выключен", messages.ERROR)
            return
        reviewer_id = request.user.pk if request.user.is_authenticated else None
        if not reviewer_id:
            self.message_user(request, "Не удалось определить модератора", messages.ERROR)
            return
        count = 0
        for change in queryset.filter(status="proposed"):
            result = processing.review_catalog_change(change.pk, "rejected", reviewer_id)
            if result.status == "rejected":
                count += 1
        self.message_user(request, f"Отклонено: {count}", messages.SUCCESS)

    @admin.action(description=_("Применить одобренные изменения"))
    def apply_changes(self, request, queryset):
        if not settings.FEATURES.get("catalog_processing", False):
            self.message_user(request, "Feature catalog_processing выключен", messages.ERROR)
            return
        actor_id = request.user.pk if request.user.is_authenticated else None
        count = 0
        for change in queryset.filter(status="approved"):
            result = processing.apply_catalog_change(change.pk, actor_id=actor_id)
            if result.status == "applied":
                count += 1
        self.message_user(request, f"Применено: {count}", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
