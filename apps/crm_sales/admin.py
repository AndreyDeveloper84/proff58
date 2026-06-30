from django.contrib import admin

from .models import Deal


class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "stage", "amount", "user", "created_at")
    list_filter = ("stage",)
    search_fields = ("title",)


def register() -> None:
    """Зарегистрировать admin (вызывается из AppConfig.ready() под флагом crm)."""
    admin.site.register(Deal, DealAdmin)
