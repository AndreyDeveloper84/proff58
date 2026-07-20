"""Админка заказов и корзины (минимальная для #26)."""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import B2BInvoice, Cart, CartItem, Order, OrderItem


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


@admin.register(B2BInvoice)
class B2BInvoiceAdmin(admin.ModelAdmin):
    """Счета B2B (#559). Оплату отмечает менеджер action'ом — он ведёт заказ и
    резерв через invoice_lifecycle (paid + confirm), а не правкой полей руками."""

    list_display = ("number", "order", "status", "issued_at", "valid_until", "paid_at")
    list_filter = ("status",)
    search_fields = ("number", "order__order_number", "order__inn", "order__company_name")
    readonly_fields = ("order", "number", "issued_at", "valid_until", "paid_at", "status")
    actions = ["mark_paid"]

    def has_add_permission(self, request):  # счёт создаёт только place_order
        return False

    @admin.action(description="Отметить оплаченным (заказ → оплачен, резерв списан)")
    def mark_paid(self, request, queryset):
        from .invoice_lifecycle import mark_invoice_paid

        done = 0
        for invoice in queryset:
            try:
                mark_invoice_paid(invoice.pk)
                done += 1
            except ValidationError as exc:
                self.message_user(request, "; ".join(exc.messages), level=messages.ERROR)
        if done:
            self.message_user(request, f"Оплачено счетов: {done}.", level=messages.SUCCESS)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "status", "ordered_at", "created_at")
    list_filter = ("status",)
    inlines = [CartItemInline]
