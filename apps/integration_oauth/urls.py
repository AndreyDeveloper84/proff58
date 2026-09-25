"""Публичные эндпоинты входа: подключаются в config/urls под /api/oauth/ (nginx → Django)."""

from django.urls import path

from . import views

app_name = "integration_oauth"

urlpatterns = [
    path("providers/", views.providers_list, name="providers"),
    path("<str:provider>/start/", views.start, name="start"),
    path("<str:provider>/callback/", views.callback, name="callback"),
]
