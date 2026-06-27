from django.contrib import admin

from .models import AiCallLog


@admin.register(AiCallLog)
class AiCallLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "capability", "status", "provider", "model",
                    "entity_ref", "tokens_out", "latency_ms")
    list_filter = ("capability", "status", "provider")
    search_fields = ("entity_ref", "input_ref", "reason")
    readonly_fields = ("output",)
    date_hierarchy = "created_at"
