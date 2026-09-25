"""Админка акций (#571): создать/выключить акцию, даты, тип выгоды, охват, код."""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import DiscountType, Promotion


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    change_list_template = "admin/promotions/promotion/change_list.html"
    save_on_top = True
    list_display = (
        "name",
        "works_now",
        "benefit",
        "kind",
        "scope",
        "is_active",
        "starts_at",
        "ends_at",
        "priority",
    )
    list_filter = ("is_active", "discount_type", "scope")
    search_fields = ("name", "promo_code")
    # Каталог большой — только autocomplete, без обычных мультиселектов.
    autocomplete_fields = ("products", "categories")
    fieldsets = (
        (None, {"fields": ("name", "is_active", ("starts_at", "ends_at"), "priority")}),
        ("Выгода", {"fields": ("discount_type", "discount_value")}),
        (
            "Охват",
            {
                "fields": ("scope", "products", "categories", "promo_code"),
                "description": (
                    "Пустой промокод — акция автоматическая. Бесплатная доставка — "
                    "только по коду (scope «Корзина»); автоматическая бесплатная "
                    "доставка настраивается в зонах («Бесплатно от суммы»)."
                ),
            },
        ),
    )

    @admin.display(description="Работает сейчас")
    def works_now(self, obj):
        """Главный вопрос про акцию — действует она или нет.

        Раньше это приходилось выводить в уме из трёх полей: галочки и двух дат.
        Причина простоя пишется рядом, чтобы не гадать, какое из них виновато.
        """
        now = timezone.now()
        if not obj.is_active:
            reason = "выключена"
        elif obj.starts_at and obj.starts_at > now:
            reason = f"начнётся {timezone.localtime(obj.starts_at):%d.%m.%Y %H:%M}"
        elif obj.ends_at and obj.ends_at < now:
            reason = f"закончилась {timezone.localtime(obj.ends_at):%d.%m.%Y}"
        else:
            # mark_safe, не format_html: подстановок нет, а argless-вызов в Django 6 убирают.
            return mark_safe(
                '<span style="color:#28a745;font-weight:700;">● да</span>'
            )  # noqa: S308
        return format_html(
            '<span style="color:#dc3545;font-weight:700;">● нет</span>'
            '<br><span style="opacity:.6;font-size:.85em;">{}</span>',
            reason,
        )

    @admin.display(description="Выгода")
    def benefit(self, obj):
        if obj.discount_type == DiscountType.PERCENT:
            return f"−{obj.discount_value:g}%"
        if obj.discount_type == DiscountType.FIXED:
            return f"−{obj.discount_value:g} ₽"
        return "бесплатная доставка"

    @admin.display(description="Как применяется")
    def kind(self, obj):
        """Автоматическая или по коду — вторая частая путаница после дат."""
        if obj.promo_code:
            return format_html(
                'по коду <code style="font-weight:700;">{}</code>', obj.promo_code.upper()
            )
        return "автоматически"
