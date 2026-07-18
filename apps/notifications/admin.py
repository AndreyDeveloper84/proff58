from django.contrib import admin

from .models import (
    Notification,
    NotificationErrorKind,
    NotificationLog,
    NotificationStatus,
    UserNotificationPreference,
)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event", "channel", "status", "error_kind", "user", "created_at")
    list_filter = ("channel", "status", "error_kind", "event")
    search_fields = ("event", "idempotency_key")
    readonly_fields = (
        "user",
        "channel",
        "event",
        "status",
        "error_message",
        "error_kind",
        "idempotency_key",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = ["retry_failed"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Повторить отправку (только retryable failed) — #521")
    def retry_failed(self, request, queryset):
        """Ручной retry только retryable FAILED (#521 AC) — permanent игнорируем
        молча тут, отчитываемся отдельно: ретраить их бессмысленно."""
        from .tasks import send_notification_task

        retryable = queryset.filter(
            status=NotificationStatus.FAILED, error_kind=NotificationErrorKind.RETRYABLE
        )
        ignored = queryset.exclude(pk__in=retryable.values_list("pk", flat=True)).count()
        requeued_ids = list(retryable.values_list("pk", flat=True))
        retryable.update(status=NotificationStatus.QUEUED, error_message="", error_kind="")
        for log_id in requeued_ids:
            send_notification_task.delay(log_id)

        self.message_user(
            request,
            f"Поставлено на повтор: {len(requeued_ids)}. "
            f"Пропущено (не retryable failed): {ignored}.",
        )


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
