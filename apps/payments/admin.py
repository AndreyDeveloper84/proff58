from django.contrib import admin

from .models import Payment, Refund


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("yookassa_refund_id", "payment__yookassa_id", "idempotency_key")
    readonly_fields = (
        "payment",
        "amount",
        "currency",
        "status",
        "yookassa_refund_id",
        "idempotency_key",
        "error_message",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("yookassa_id", "order", "method", "status", "amount", "created_at")
    list_filter = ("status", "method")
    search_fields = ("yookassa_id", "order__order_number")
    readonly_fields = (
        "yookassa_id",
        "order",
        "method",
        "status",
        "amount",
        "currency",
        "confirmation_url",
        "idempotency_key",
        "webhook_payload",
        "paid_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
