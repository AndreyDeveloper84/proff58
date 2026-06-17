from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from .models import (
    Attribute,
    AttributeOption,
    Category,
    CategoryAttribute,
    CategoryMappingRule,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
)


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 2


class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 1
    autocomplete_fields = ["attribute"]


@admin.register(Category)
class CategoryAdmin(TreeAdmin):
    form = movenodeform_factory(Category)
    list_display = ("name", "slug", "is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    inlines = [CategoryAttributeInline]


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "attribute_type", "unit", "is_filterable")
    list_filter = ("attribute_type", "is_filterable")
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

    @admin.action(description=_("Опубликовать выбранные товары"))
    def action_publish(self, request, queryset):
        updated = queryset.update(status=ProductStatus.PUBLISHED, is_active=True)
        self.message_user(request, _("Опубликовано: %d") % updated)

    @admin.action(description=_("Вернуть на проверку"))
    def action_needs_review(self, request, queryset):
        updated = queryset.update(status=ProductStatus.NEEDS_REVIEW)
        self.message_user(request, _("Отправлено на проверку: %d") % updated)
