"""Админка акций (#571): создать/выключить акцию, даты, тип выгоды, охват, код."""

from django.contrib import admin

from .models import Promotion


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "scope",
        "discount_type",
        "discount_value",
        "promo_code",
        "is_active",
        "starts_at",
        "ends_at",
        "priority",
    )
    list_filter = ("is_active", "discount_type", "scope")
    search_fields = ("name", "promo_code")
    # Каталог большой — только autocomplete, без обычных мультиселектов.
    autocomplete_fields = ("products", "categories")
    fieldsets = (
        (None, {"fields": ("name", "is_active", ("starts_at", "ends_at"), "priority")}),
        ("Выгода", {"fields": ("discount_type", "discount_value")}),
        (
            "Охват",
            {
                "fields": ("scope", "products", "categories", "promo_code"),
                "description": (
                    "Пустой промокод — акция автоматическая. Бесплатная доставка — "
                    "только по коду (scope «Корзина»); автоматическая бесплатная "
                    "доставка настраивается в зонах («Бесплатно от суммы»)."
                ),
            },
        ),
    )
