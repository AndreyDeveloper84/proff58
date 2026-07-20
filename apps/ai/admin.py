from django.contrib import admin, messages

from apps.catalog.models import EnrichStatus, ModerationProduct

from . import services
from .models import AiCallLog, ContentFinding, ExternalCall, FindingEvidence


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

    def has_add_permission(self, request, obj=None):
        return False


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
        rid = request.user.pk if request and request.user.is_authenticated else None
        applied = skipped = errors = 0
        for f in queryset:
            if f.selected_evidence_id is None:
                skipped += 1
                continue
            try:
                res = services.approve_and_apply_finding(f.pk, f.selected_evidence_id, rid)
                applied += 1 if res.status == "applied" else 0
            except Exception:  # noqa: BLE001 — частичный успех (#367)
                errors += 1
        if request is not None:
            msg = f"Применено: {applied}; без evidence: {skipped}"
            if errors:
                msg += f"; ошибок: {errors}"
                self.message_user(request, msg, messages.WARNING)
            else:
                self.message_user(request, msg, messages.INFO)


@admin.register(ExternalCall)
class ExternalCallAdmin(admin.ModelAdmin):
    """Вызовы внешних источников (#432/M-09): ручная сверка UNKNOWN.

    UNKNOWN держит резерв дневного бюджета до сверки человеком (вызов мог пройти
    и оплатиться — авто-решение запрещено спекой §6.5). Оператор проверяет у
    провайдера, прошёл ли вызов, и выбирает действие ниже.
    """

    list_display = (
        "id",
        "run",
        "adapter",
        "status",
        "reserved_cost",
        "reserved_day",
        "attempt_count",
        "finished_at",
    )
    list_filter = ("status", "adapter")
    search_fields = ("run__idempotency_key", "provider_idempotency_key")
    readonly_fields = [f.name for f in ExternalCall._meta.fields]
    actions = ["resolve_unknown_as_error", "resolve_unknown_as_paid"]

    def has_add_permission(self, request):
        return False

    def _resolve(self, request, queryset, outcome, verb):
        done = skipped = 0
        for call in queryset:
            if services.resolve_unknown_call(call.pk, outcome=outcome):
                done += 1
            else:
                skipped += 1
        msg = f"{verb}: {done}"
        if skipped:
            msg += f"; пропущено (не unknown): {skipped}"
        self.message_user(request, msg, messages.INFO if done else messages.WARNING)

    @admin.action(description="Сверка UNKNOWN: вызов НЕ прошёл → error, резерв снять")
    def resolve_unknown_as_error(self, request, queryset):
        self._resolve(request, queryset, "error", "Резерв снят")

    @admin.action(description="Сверка UNKNOWN: вызов прошёл и оплачен → ok, резерв в расход")
    def resolve_unknown_as_paid(self, request, queryset):
        self._resolve(request, queryset, "ok", "Списано в расход")
