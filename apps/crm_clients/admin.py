from django.contrib import admin

from .models import ClientProfile, Interaction


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0
    readonly_fields = ("created_at",)


class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "source", "created_at")
    search_fields = ("user__phone", "user__full_name")
    inlines = [InteractionInline]


def register() -> None:
    """Зарегистрировать admin (вызывается из AppConfig.ready() под флагом crm)."""
    admin.site.register(ClientProfile, ClientProfileAdmin)
