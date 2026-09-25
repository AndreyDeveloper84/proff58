from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .contacts import CONTACT_FIELDS
from .models import SiteSettings


class SiteSettingsForm(forms.ModelForm):
    """Контакты — отдельными полями (T3): менеджер не правит JSON руками.
    Значения пишутся в ``contacts`` под теми ключами, которые читает витрина;
    прочие ключи JSON сохраняются как есть."""

    class Meta:
        model = SiteSettings
        fields = (
            "name",
            "logo",
            "primary_color",
            "accent_color",
            "requisites",
            "region",
            "reviews_enabled",
            "b2b_enabled",
            "promotions_enabled",
            "articles_enabled",
            "max_chat_enabled",
            "ai_assist_enabled",
            "video_reviews_enabled",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contacts = self.instance.contacts if isinstance(self.instance.contacts, dict) else {}
        for key, (label, _default) in CONTACT_FIELDS.items():
            self.fields[f"contact_{key}"] = forms.CharField(
                label=label, required=False, initial=str(contacts.get(key) or "")
            )

    def save(self, commit=True):
        contacts = dict(self.instance.contacts) if isinstance(self.instance.contacts, dict) else {}
        for key in CONTACT_FIELDS:
            contacts[key] = (self.cleaned_data.get(f"contact_{key}") or "").strip()
        self.instance.contacts = contacts
        return super().save(commit=commit)


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
    form = SiteSettingsForm
    fieldsets = (
        (_("Бренд"), {"fields": ("name", "logo", "primary_color", "accent_color")}),
        (
            _("Контакты"),
            {
                "description": _(
                    "Показываются в шапке, подвале, чекауте и карточке товара. "
                    "Витрина обновляет их в течение минуты."
                ),
                "fields": tuple(f"contact_{k}" for k in CONTACT_FIELDS) + ("region",),
            },
        ),
        (_("Реквизиты"), {"fields": ("requisites",)}),
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
