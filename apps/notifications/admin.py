from django.contrib import admin

from .models import Notification, NotificationLog, UserNotificationPreference


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


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    """Редактируемо — саппорт иногда правит настройки по запросу пользователя."""

    list_display = (
        "user",
        "max_enabled",
        "order_updates_enabled",
        "product_availability_enabled",
        "marketing_enabled",
    )
    search_fields = ("user__phone", "user__email")
    readonly_fields = ("marketing_consent_at", "marketing_consent_version")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Read-only — системный intent/история, как и NotificationLog."""

    list_display = ("event", "category", "user", "policy_skip_reason", "read_at", "created_at")
    list_filter = ("category", "event")
    search_fields = ("event", "idempotency_key")
    readonly_fields = (
        "user",
        "event",
        "category",
        "title",
        "body",
        "data",
        "template_version",
        "idempotency_key",
        "delivery",
        "policy_skip_reason",
        "read_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
