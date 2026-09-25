from django.contrib import admin

from .models import Task


class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "assignee", "due_date", "created_at")
    list_filter = ("status",)
    search_fields = ("title",)


def register() -> None:
    """Зарегистрировать admin (вызывается из AppConfig.ready() под флагом crm)."""
    admin.site.register(Task, TaskAdmin)
