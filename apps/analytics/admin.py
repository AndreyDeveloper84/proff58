from django.contrib import admin

from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "session_id", "user", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("session_id",)
    readonly_fields = ("event_type", "session_id", "user", "payload", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
