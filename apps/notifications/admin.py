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
    list_display = ("event", "channel", "status", "error_kind", "user", "subject", "created_at")
    list_filter = ("channel", "status", "error_kind", "event")
    search_fields = ("event", "idempotency_key", "subject", "recipients")
    readonly_fields = (
        "user",
        "channel",
        "event",
        "status",
        "error_message",
        "error_kind",
        "idempotency_key",
        "subject",
        "recipients",
        "text_masked",
        "created_at",
        "updated_at",
    )
    exclude = ("text", "chat_id")

    @admin.display(description="Текст")
    def text_masked(self, obj):
        """Текст письма без гостевого токена в ссылке: `?t=…` — доступ к заказу,
        сотрудникам с правом на журнал он не нужен (DRF-2299)."""
        import re

        return re.sub(r"([?&]t=)[\w-]+", r"\1…", obj.text or "")

    date_hierarchy = "created_at"
    actions = ["retry_failed"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Повторить отправку (retryable/неклассиф. failed) — #521")
    def retry_failed(self, request, queryset):
        """Ручной retry FAILED (#521 AC) — permanent игнорируем молча: ретраить
        их бессмысленно (4xx кроме 429 — сам запрос некорректен).

        Неклассифицированные (error_kind="", попали в generic except в
        tasks.py — баг channels/max.py, а не провайдерская ошибка) ТОЖЕ
        retryable здесь: автоматический retry Celery уже обходится с ними как
        с retryable (bounded backoff), человек, нажавший «повторить» в
        админке, тем более принял осознанное решение — не должно быть тупика,
        когда Celery исчерпал попытки, а админка такую строку не видит вообще.
        """
        from .services import enqueue

        retryable = queryset.filter(status=NotificationStatus.FAILED).exclude(
            error_kind=NotificationErrorKind.PERMANENT
        )
        ignored = queryset.exclude(pk__in=retryable.values_list("pk", flat=True)).count()
        requeued_ids = list(retryable.values_list("pk", flat=True))
        retryable.update(status=NotificationStatus.QUEUED, error_message="", error_kind="")
        # DRF-2293: через enqueue — при недоступной очереди строка вернётся в
        # failed/retryable, а не зависнет в QUEUED, и действие не упадёт 500.
        not_enqueued = 0
        for log in NotificationLog.objects.filter(pk__in=requeued_ids):
            if enqueue(log).status != NotificationStatus.QUEUED:
                not_enqueued += 1

        message = (
            f"Поставлено на повтор: {len(requeued_ids) - not_enqueued}. "
            f"Пропущено (permanent/не failed): {ignored}."
        )
        if not_enqueued:
            message += f" Очередь недоступна для {not_enqueued} — повторите позже."
        self.message_user(request, message)


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
