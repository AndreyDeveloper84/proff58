"""Админка заказов и корзины (минимальная для #26)."""

from django.contrib import admin

from .models import Cart, CartItem, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "code_1c",
        "article",
        "name",
        "unit",
        "price_base",
        "price_final",
        "discount",
        "price_type",
        "currency",
        "quantity",
        "line_total",
    )
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "display_status",
        "fulfillment_status",
        "payment_status",
        "sync_1c_status",
        "total",
        "currency",
        "created_at",
    )
    list_filter = ("fulfillment_status", "payment_status", "sync_1c_status", "customer_type")
    search_fields = ("order_number", "customer_name", "customer_phone", "inn")
    inlines = [OrderItemInline]
    readonly_fields = ("display_status", "created_at", "updated_at")

    @admin.display(description="Статус для клиента")
    def display_status(self, obj):
        return obj.display_status


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "status", "ordered_at", "created_at")
    list_filter = ("status",)
    inlines = [CartItemInline]
