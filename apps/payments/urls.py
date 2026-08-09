from django.urls import path

from . import api, views

app_name = "payments"

urlpatterns = [
    path("webhook/yookassa/", views.yookassa_webhook, name="yookassa-webhook"),
    path("orders/<str:number>/", api.OrderPaymentView.as_view(), name="order-payment"),
]
