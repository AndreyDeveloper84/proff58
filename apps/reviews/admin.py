"""Админка-модерация отзывов (#573): одобрить/отклонить с причиной.

Образец — ContentFindingAdmin (apps/ai/admin.py): массовые actions + причина
отклонения. Queryset не сужаем до pending (модератору нужен и архив) — статус
в фильтрах; причина обязательна для rejected (валидация формы).
"""

from django import forms
from django.contrib import admin, messages
from django.utils import timezone

from apps.orders.reviews_bridge import order_products_summary

from .models import Review, ReviewStatus


class ReviewAdminForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["status", "rejection_reason"]

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("status") == ReviewStatus.REJECTED
            and not (cleaned.get("rejection_reason") or "").strip()
        ):
            raise forms.ValidationError(
                {"rejection_reason": "Укажите причину отклонения — покупатель её увидит."}
            )
        return cleaned


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    form = ReviewAdminForm
    list_display = (
        "order",
        "author_name",
        "product_rating",
        "delivery_rating",
        "shop_rating",
        "status",
        "created_at",
    )
    list_select_related = ("order", "author")
    list_filter = ("status", "product_rating")
    search_fields = ("order__order_number", "author_name", "text")
    readonly_fields = (
        "order",
        "author",
        "author_name",
        "order_products",
        "product_rating",
        "delivery_rating",
        "shop_rating",
        "text",
        "created_at",
        "moderated_at",
    )
    fields = (
        "order",
        "author",
        "author_name",
        "order_products",
        "product_rating",
        "delivery_rating",
        "shop_rating",
        "text",
        "status",
        "rejection_reason",
        "created_at",
        "moderated_at",
    )
    actions = ["approve_selected", "reject_selected"]

    def has_add_permission(self, request):  # отзыв создаёт только покупатель через API
        return False

    @admin.display(description="Состав заказа")
    def order_products(self, obj):
        return ", ".join(order_products_summary(obj.order_id)) or "—"

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            obj.moderated_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description="Одобрить выбранные")
    def approve_selected(self, request, queryset):
        n = queryset.exclude(status=ReviewStatus.APPROVED).update(
            status=ReviewStatus.APPROVED, rejection_reason="", moderated_at=timezone.now()
        )
        self.message_user(request, f"Опубликовано отзывов: {n}.", messages.SUCCESS)

    @admin.action(description="Отклонить выбранные (типовая причина)")
    def reject_selected(self, request, queryset):
        n = queryset.exclude(status=ReviewStatus.REJECTED).update(
            status=ReviewStatus.REJECTED,
            rejection_reason="Отклонено модератором.",
            moderated_at=timezone.now(),
        )
        self.message_user(
            request,
            f"Отклонено отзывов: {n}. Индивидуальная причина — в карточке отзыва.",
            messages.SUCCESS,
        )
