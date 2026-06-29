from django.urls import path

from . import webhook

app_name = "integration_max"

urlpatterns = [
    path("webhook/", webhook.webhook, name="webhook"),
]
