from django.contrib import admin

from .models import Deal


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "stage", "amount", "user", "created_at")
    list_filter = ("stage",)
    search_fields = ("title",)
