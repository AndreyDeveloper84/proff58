from django.contrib import admin
from django.utils import timezone

from .models import Review, ReviewStatus


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["__str__", "subject_type", "subject_id", "rating", "status", "created_at"]
    list_filter = ["status", "subject_type", "rating"]
    search_fields = ["author_name", "body", "author__email"]
    readonly_fields = ["created_at", "updated_at", "moderated_at"]
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Одобрить выбранные отзывы")
    def approve_reviews(self, request, queryset):
        queryset.update(status=ReviewStatus.APPROVED, moderated_at=timezone.now())

    @admin.action(description="Отклонить выбранные отзывы")
    def reject_reviews(self, request, queryset):
        queryset.update(status=ReviewStatus.REJECTED, moderated_at=timezone.now())
