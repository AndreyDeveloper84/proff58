from django.urls import path

from .api import DeliveryZonesView

app_name = "delivery"

urlpatterns = [
    path("zones/", DeliveryZonesView.as_view(), name="zones"),
]
