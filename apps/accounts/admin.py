from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core import events

from .models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    ordering = ("phone",)
    list_display = ("phone", "email", "full_name", "customer_type", "is_b2b_verified", "is_staff")
    list_filter = ("customer_type", "is_staff", "is_active")
    search_fields = ("phone", "email", "full_name")
    actions = ["verify_b2b_action"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Личные данные", {"fields": ("full_name", "email", "customer_type")}),
        (
            "Права",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone", "email", "customer_type", "password1", "password2"),
            },
        ),
    )

    @admin.action(description="Верифицировать B2B-организацию")
    def verify_b2b_action(self, request, queryset):
        verified = 0
        skipped = 0
        for user in queryset.filter(customer_type="b2b"):
            profile, _ = Profile.objects.get_or_create(user=user)
            if not profile.is_b2b_verified:
                profile.is_b2b_verified = True
                profile.save(update_fields=["is_b2b_verified"])
                events.b2b_verified.send(
                    sender=self.__class__,
                    user_id=user.pk,
                    organization_id=profile.pk,
                )
                verified += 1
            else:
                skipped += 1
        if verified:
            self.message_user(request, f"Верифицировано: {verified}.", messages.SUCCESS)
        if skipped:
            self.message_user(
                request, f"Уже верифицированы (пропущено): {skipped}.", messages.WARNING
            )
