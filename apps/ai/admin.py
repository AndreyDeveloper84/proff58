from django.contrib import admin, messages

from apps.catalog.models import EnrichStatus, ModerationProduct

from . import services
from .models import AiCallLog, ContentFinding, FindingEvidence


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


# --- sourcing admin ---


class FindingEvidenceInline(admin.TabularInline):
    model = FindingEvidence
    extra = 0
    readonly_fields = (
        "external_call",
        "source_name",
        "confidence",
        "observed_value_hash",
        "observed_source",
        "canonical_url",
        "observed_at",
    )
    can_delete = False


@admin.register(ContentFinding)
class ContentFindingAdmin(admin.ModelAdmin):
    list_display = (
        "product_ref",
        "target_kind",
        "attribute_slug",
        "source_name",
        "confidence",
        "status",
        "last_outcome",
    )
    list_filter = ("status", "source_name", "target_kind")
    search_fields = ("product_ref", "attribute_slug")
    inlines = [FindingEvidenceInline]
    actions = ["reject_selected", "approve_selected"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=ContentFinding.Status.PENDING)

    @admin.action(description="Отклонить выбранные")
    def reject_selected(self, request, queryset):
        n = queryset.update(
            status=ContentFinding.Status.REJECTED, rejection_reason="отклонено модератором"
        )
        if request is not None:
            self.message_user(request, f"Отклонено: {n}", messages.SUCCESS)

    @admin.action(description="Одобрить (по выбранному evidence)")
    def approve_selected(self, request, queryset):
        rid = getattr(getattr(request, "user", None), "pk", None)
        applied = skipped = failed = 0
        for f in queryset:
            if f.selected_evidence_id is None:
                skipped += 1
                continue
            try:
                res = services.approve_and_apply_finding(f.pk, f.selected_evidence_id, rid)
            except Exception:  # noqa: BLE001 — сбой одной находки не рвёт bulk (частичный успех)
                failed += 1
                continue
            applied += 1 if res.status == "applied" else 0
        if request is not None:
            self.message_user(
                request,
                f"Применено: {applied}; без evidence: {skipped}; ошибок: {failed}",
                messages.INFO,
            )
