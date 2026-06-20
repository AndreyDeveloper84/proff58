from django.contrib import admin
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from apps.core.events import EventSource, product_created, product_updated

from .models import (
    Attribute,
    AttributeOption,
    Category,
    CategoryAttribute,
    CategoryMappingRule,
    EnrichmentLog,
    ImportRun,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
)


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 2
    prepopulated_fields = {"slug": ("value",)}


class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 1
    autocomplete_fields = ["attribute"]
    fields = ("attribute", "is_filter", "filter_kind", "is_seo_facet", "is_required", "sort_order")


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
    list_display = ("name", "slug", "attribute_type", "unit", "is_filterable", "is_ai_feature")
    list_filter = ("attribute_type", "is_filterable", "is_ai_feature")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [AttributeOptionInline]


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
                "fields": (
                    "price",
                    "old_price",
                    "currency",
                    "stock_quantity",
                    "reserved_quantity",
                    "available_quantity",
                    "stock_status",
                    "price_updated_at",
                    "stock_updated_at",
                )
            },
        ),
        (_("SEO"), {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
        (
            _("Служебное"),
            {"fields": ("attrs_cache", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    inlines = [ProductImageInline, ProductAttributeValueInline]

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
