from django.urls import path

from .api import DeliverySlotsView, DeliveryZonesView

app_name = "delivery"

urlpatterns = [
    path("zones/", DeliveryZonesView.as_view(), name="zones"),
    path("slots/", DeliverySlotsView.as_view(), name="slots"),
]
