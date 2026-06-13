from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    ordering = ("phone",)
    list_display = ("phone", "email", "full_name", "customer_type", "is_staff")
    list_filter = ("customer_type", "is_staff", "is_active")
    search_fields = ("phone", "email", "full_name")
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
