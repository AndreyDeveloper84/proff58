"""Админка привязок VK ID / Яндекс ID: просмотр и отвязка (удаление записи)."""

from django.contrib import admin

from .models import OAuthAccount


@admin.register(OAuthAccount)
class OAuthAccountAdmin(admin.ModelAdmin):
    list_display = ("provider", "provider_user_id", "user", "email", "linked_at", "last_login_at")
    list_filter = ("provider",)
    search_fields = ("email", "provider_user_id")
    list_select_related = ("user",)
    raw_id_fields = ("user",)
    readonly_fields = (
        "user",
        "provider",
        "provider_user_id",
        "email",
        "full_name",
        "linked_at",
        "last_login_at",
    )

    def has_add_permission(self, request):
        # Привязка появляется только из колбэка провайдера: вручную заведённая
        # запись с чужим provider_user_id означала бы вход в чужой аккаунт.
        return False

    # Удаление записи = отвязка. Оставляем штатное право delete: оператор может
    # снять привязку, если пользователь потерял доступ к аккаунту провайдера.
