"""Админка доставки: зоны, пункты самовывоза, слоты доставки."""

from django.contrib import admin

from .models import DeliverySlot, DeliveryZone, PickupPoint


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


@admin.register(DeliverySlot)
class DeliverySlotAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "starts_at",
        "ends_at",
        "delivery_method",
        "zone",
        "capacity",
        "booked",
        "is_active",
    )
    list_filter = ("is_active", "delivery_method", "zone")
    list_editable = ("capacity", "is_active")
    date_hierarchy = "date"
    ordering = ("-date", "starts_at")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("zone")

    @admin.display(description="Занято")
    def booked(self, obj) -> int:
        # Не reverse-ORM в таблицу заказов: единственная точка подсчёта
        # занятости — apps.orders.slots (CLAUDE.md §4).
        from apps.orders.slots import occupied_count

        return occupied_count(obj.pk)
