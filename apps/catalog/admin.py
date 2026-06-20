from django.contrib import admin
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from apps.core.events import EventSource, product_created, product_updated
from apps.pricing.services import WHOLESALE, price_for
from apps.sync_1c.models import PriceRecord

from .models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    CategoryMappingRule,
    EnrichmentLog,
    ImportRun,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
    Source,
)


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 2
    prepopulated_fields = {"slug": ("value",)}


class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 1
    autocomplete_fields = ["attribute"]
    fields = ("attribute", "is_filter", "is_seo_facet", "is_required", "sort_order")


@admin.register(Category)
class CategoryAdmin(TreeAdmin):
    form = movenodeform_factory(Category)
    list_display = ("name", "slug", "external_id_1c", "on_site", "is_active", "sort_order")
    list_filter = ("on_site", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug", "external_id_1c")
    inlines = [CategoryAttributeInline]


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
    list_display = ("priority", "rule_type", "pattern", "brand", "target_category", "is_active")
    list_filter = ("rule_type", "is_active", "target_category")
    search_fields = ("pattern", "brand", "note")
    list_editable = ("is_active",)
    autocomplete_fields = ["target_category"]
    ordering = ("priority", "id")


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


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "article",
        "brand",
        "category",
        "status",
        "stock_status",
        "price",
        "current_wholesale",
        "is_active",
    )
    list_filter = ("status", UncategorizedFilter, "stock_status", "is_active", "brand")
    search_fields = ("name", "original_name", "article", "code_1c", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["category"]
    list_select_related = ("category",)
    readonly_fields = (
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
    actions = ["action_publish", "action_needs_review"]
    fieldsets = (
        (None, {"fields": ("name", "slug", "status", "is_active")}),
        (
            _("Категория сайта"),
            {"fields": ("category", "category_is_manual", "matched_rule")},
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
    inlines = [ProductImageInline, ProductAttributeValueInline, CurrentPriceInline]

    def get_queryset(self, request):
        # Текущая оптовая цена — подзапросом, чтобы колонка списка не делала N+1.
        wholesale = PriceRecord.objects.filter(
            product=OuterRef("pk"), price_type=WHOLESALE, is_current=True
        ).values("value")[:1]
        return super().get_queryset(request).annotate(_wholesale_price=Subquery(wholesale))

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

    @admin.action(description=_("Опубликовать выбранные товары"))
    def action_publish(self, request, queryset):
        # Только реально меняющиеся: уже опубликованные и активные пропускаем.
        qs = queryset.exclude(status=ProductStatus.PUBLISHED, is_active=True)
        ids = list(qs.values_list("id", flat=True))
        updated = qs.update(status=ProductStatus.PUBLISHED, is_active=True)
        if ids:
            self._emit_bulk_updated(ids, ["status", "is_active"])
        self.message_user(request, _("Опубликовано: %d") % updated)

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
