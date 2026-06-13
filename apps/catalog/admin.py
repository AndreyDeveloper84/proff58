from django.contrib import admin
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from .models import (
    Attribute,
    AttributeOption,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductImage,
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


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    autocomplete_fields = ["attribute"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "article", "code_1c", "category", "is_active", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("name", "article", "code_1c", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("attrs_cache", "created_at", "updated_at")
    inlines = [ProductImageInline, ProductAttributeValueInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "category", "is_active")}),
        ("Связь с 1С", {"fields": ("code_1c", "article")}),
        ("Контент", {"fields": ("short_description", "description")}),
        ("SEO", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
        ("Кэш", {"fields": ("attrs_cache",), "classes": ("collapse",)}),
        ("Даты", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
