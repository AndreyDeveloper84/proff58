"""Админка заявок по товарам — модерация."""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import InquiryStatus, ProductInquiry


@admin.register(ProductInquiry)
class ProductInquiryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "phone", "product", "status")
    list_filter = ("status", "kind")
    search_fields = ("phone", "name", "product__name")
    raw_id_fields = ("product",)
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_processed",)

    @admin.action(description=_("Отметить обработанными"))
    def mark_processed(self, request, queryset):
        queryset.update(status=InquiryStatus.PROCESSED)
