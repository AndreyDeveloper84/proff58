from django.contrib import admin

from .models import Payment, Refund


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("provider_refund_id", "payment__provider_order_id", "idempotency_key")
    readonly_fields = (
        "payment",
        "amount",
        "currency",
        "status",
        "provider_refund_id",
        "idempotency_key",
        "error_message",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "provider_order_id",
        "order",
        "provider",
        "status",
        "amount",
        "receipt_status",
        "created_at",
    )
    list_filter = ("status", "provider", "method", "receipt_status")
    search_fields = (
        "provider_order_id",
        "provider_payment_id",
        "order__order_number",
    )
    readonly_fields = (
        "provider",
        "provider_order_id",
        "provider_payment_id",
        "order",
        "method",
        "status",
        "amount",
        "currency",
        "confirmation_url",
        "idempotency_key",
        "webhook_payload",
        "paid_at",
        "receipt_id",
        "receipt_status",
        "receipt_error",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
