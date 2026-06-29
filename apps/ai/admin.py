from django.contrib import admin, messages

from apps.catalog.models import EnrichStatus, ModerationProduct

from .models import AiCallLog


@admin.register(AiCallLog)
class AiCallLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "capability",
        "status",
        "provider",
        "model",
        "entity_ref",
        "tokens_out",
        "latency_ms",
    )
    list_filter = ("capability", "status", "provider")
    search_fields = ("entity_ref", "input_ref", "reason")
    readonly_fields = ("output",)
    date_hierarchy = "created_at"


@admin.register(ModerationProduct)
class ModerationQueueAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "brand",
        "enrich_status",
        "content_source",
        "content_confidence",
        "available_quantity",
    )
    list_filter = ("content_source", "category")
    search_fields = ("name", "original_name", "article")
    actions = ["approve_content", "reject_and_reenrich"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(enrich_status=EnrichStatus.MODERATION)

    @admin.action(description="Одобрить контент (lock + done)")
    def approve_content(self, request, queryset):
        n = queryset.update(enrich_status=EnrichStatus.DONE, content_locked=True)
        if request is not None:
            self.message_user(request, f"Одобрено: {n}", messages.SUCCESS)

    @admin.action(description="Отклонить и переобогатить")
    def reject_and_reenrich(self, request, queryset):
        for product in queryset:
            product.description = ""
            product.short_description = ""
            product.enrich_status = EnrichStatus.PENDING
            product.save(update_fields=["description", "short_description", "enrich_status"])
