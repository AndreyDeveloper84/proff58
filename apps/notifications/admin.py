from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event", "channel", "status", "user", "created_at")
    list_filter = ("channel", "status", "event")
    search_fields = ("event", "idempotency_key")
    readonly_fields = (
        "user",
        "channel",
        "event",
        "status",
        "error_message",
        "idempotency_key",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
