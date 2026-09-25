@admin.register(ProductAvailabilitySubscription)
class ProductAvailabilitySubscriptionAdmin(admin.ModelAdmin):
    """Read-only — жизненный цикл ведёт apps.catalog.availability_subscriptions,
    не ручное редактирование (как NotificationLog/Notification, #514/#515)."""

    list_display = ("user", "product", "channel", "status", "subscribed_at", "notified_at")
    list_filter = ("channel", "status")
    search_fields = ("user__phone", "product__name", "product__article")
    readonly_fields = (
        "user",
        "product",
        "channel",
        "status",
        "subscribed_at",
        "queued_at",
        "notified_at",
        "cancelled_at",
    )
    date_hierarchy = "subscribed_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Catalog processing audit admin
# ---------------------------------------------------------------------------


class CatalogProcessingItemInline(admin.TabularInline):
    model = CatalogProcessingItem
    extra = 0
    readonly_fields = (
        "product",
        "product_ref",
        "status",
        "input_hash",
        "baseline_hashes",
        "needed_targets",
        "error_code",
        "error_detail",
        "created_at",
        "finished_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CatalogProcessingRun)
class CatalogProcessingRunAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "mode", "status", "idempotency_key", "created_at", "finished_at")
    list_filter = ("kind", "mode", "status")
    search_fields = ("idempotency_key",)
    readonly_fields = (
        "id",
        "kind",
        "mode",
        "status",
        "idempotency_key",
        "scope",
        "ruleset_version",
        "ruleset_hash",
        "taxonomy_hash",
        "stats",
        "created_by",
        "created_at",
        "finished_at",
    )
    inlines = [CatalogProcessingItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogProcessingItem)
class CatalogProcessingItemAdmin(admin.ModelAdmin):
    list_display = ("run", "product_ref", "status", "input_hash", "created_at", "finished_at")
    list_filter = ("status", "run__kind", "run__mode")
    search_fields = ("product_ref", "run__idempotency_key")
    readonly_fields = (
        "run",
        "product",
        "product_ref",
        "status",
        "input_snapshot",
        "input_hash",
        "baseline_hashes",
        "needed_targets",
        "error_code",
        "error_detail",
        "created_at",
        "finished_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogChange)
class CatalogChangeAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "target_kind",
        "status",
        "source",
        "confidence",
        "reason_code",
        "created_at",
        "applied_at",
    )
    list_filter = ("status", "source", "target_kind")
    search_fields = ("idempotency_key", "product_ref")
    readonly_fields = (
        "id",
        "item",
        "product_ref",
        "target_kind",
        "target_key",
        "status",
        "idempotency_key",
        "before_value",
        "proposed_value",
        "after_value",
        "baseline_hash",
        "source",
        "confidence",
        "rule_ref",
        "ruleset_hash",
        "reason_code",
        "reason_detail",
        "evidence",
        "reviewed_by",
        "reviewed_at",
        "applied_at",
        "reversal_of",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
