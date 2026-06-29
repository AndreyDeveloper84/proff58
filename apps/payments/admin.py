from django.contrib import admin

from .models import Payment


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
