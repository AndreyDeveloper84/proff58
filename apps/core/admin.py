from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import SiteSettings


class TimestampColumnsMixin:
    """Русские подписи столбцов дат для наследников TimeStampedModel.

    У `created_at`/`updated_at` намеренно нет verbose_name (см. TimeStampedModel —
    иначе миграция в каждом приложении), поэтому админка подписывала столбцы
    «Created at» / «Updated at». В list_display вместо полей ставим `created` /
    `updated`: подпись русская, сортировка по клику сохраняется.
    """

    @admin.display(description="Создано", ordering="created_at")
    def created(self, obj):
        return obj.created_at

    @admin.display(description="Изменено", ordering="updated_at")
    def updated(self, obj):
        return obj.updated_at


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (_("Бренд"), {"fields": ("name", "logo", "primary_color", "accent_color")}),
        (_("Контакты и реквизиты"), {"fields": ("contacts", "requisites", "region")}),
        (
            _("Бизнес-модули (feature-флаги)"),
            {
                "fields": (
                    "reviews_enabled",
                    "b2b_enabled",
                    "promotions_enabled",
                    "articles_enabled",
                    "max_chat_enabled",
                    "ai_assist_enabled",
                    "video_reviews_enabled",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        # Singleton: добавить можно, только если записи ещё нет.
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
