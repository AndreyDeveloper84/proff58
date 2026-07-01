from django.urls import path

from .api import ThemeView

app_name = "core"

urlpatterns = [
    path("theme/", ThemeView.as_view(), name="theme"),
]
