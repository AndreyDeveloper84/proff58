from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("webhook/yookassa/", views.yookassa_webhook, name="yookassa-webhook"),
]
