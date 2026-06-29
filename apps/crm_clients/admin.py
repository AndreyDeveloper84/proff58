from django.contrib import admin

from .models import ClientProfile, Interaction


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "source", "created_at")
    search_fields = ("user__phone", "user__full_name")
    inlines = [InteractionInline]
