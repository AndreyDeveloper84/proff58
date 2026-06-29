"""Админка доставки: зоны и пункты самовывоза."""

from django.contrib import admin

from .models import DeliveryZone, PickupPoint


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "delivery_type", "price", "free_from", "sort_order", "is_active")
    list_filter = ("delivery_type", "is_active")
    list_editable = ("price", "free_from", "sort_order", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PickupPoint)
class PickupPointAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "working_hours", "is_active")
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("name", "address")
