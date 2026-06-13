from django.contrib import admin

from .models import NomenclatureStaging, PriceRecord, StockRecord, SyncLog


@admin.register(NomenclatureStaging)
class NomenclatureStagingAdmin(admin.ModelAdmin):
    list_display = ("code_1c", "article", "name_1c", "price", "stock", "status", "imported_at")
    list_filter = ("status",)
    search_fields = ("code_1c", "article", "name_1c")
    readonly_fields = ("raw_payload", "imported_at", "processed_at")
    list_select_related = ("product",)


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ("code_1c", "price_type", "value", "currency", "is_current", "valid_from")
    list_filter = ("price_type", "is_current", "currency")
    search_fields = ("code_1c",)


@admin.register(StockRecord)
class StockRecordAdmin(admin.ModelAdmin):
    list_display = ("code_1c", "warehouse", "quantity", "updated_at")
    list_filter = ("warehouse",)
    search_fields = ("code_1c",)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("sync_type", "result", "rows_total", "rows_ok", "rows_error", "started_at")
    list_filter = ("sync_type", "result")
    readonly_fields = ("started_at", "finished_at", "error_details")
