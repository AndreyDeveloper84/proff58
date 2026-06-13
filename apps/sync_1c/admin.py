from django.contrib import admin

from .models import NomenclatureStaging, PriceRecord, StockRecord, SyncLog


@admin.register(NomenclatureStaging)
class NomenclatureStagingAdmin(admin.ModelAdmin):
    list_display = (
        "code_1c",
        "article",
        "name_1c",
        "product",
        "price",
        "stock",
        "status",
        "imported_at",
    )
    list_filter = ("status", "sync_log__sync_type", "source_file")
    search_fields = ("code_1c", "article", "name_1c", "row_hash")
    readonly_fields = (
        "raw_payload",
        "row_hash",
        "sync_log",
        "source_file",
        "imported_at",
        "processed_at",
    )
    list_select_related = ("product", "sync_log")


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "code_1c",
        "product",
        "price_type",
        "value",
        "currency",
        "is_current",
        "valid_from",
    )
    list_filter = ("is_current", "price_type", "currency")
    search_fields = ("code_1c",)
    list_select_related = ("product",)


@admin.register(StockRecord)
class StockRecordAdmin(admin.ModelAdmin):
    list_display = ("code_1c", "product", "warehouse", "quantity", "updated_at")
    list_filter = ("warehouse",)
    search_fields = ("code_1c",)
    list_select_related = ("product",)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "batch_uid",
        "sync_type",
        "source_file",
        "result",
        "rows_total",
        "rows_ok",
        "rows_error",
        "started_at",
    )
    list_filter = ("sync_type", "result")
    search_fields = ("batch_uid", "source_file")
    readonly_fields = ("batch_uid", "started_at", "finished_at", "error_details")
