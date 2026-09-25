from django.urls import path

from .api import CdekCitiesView, CdekPointsView, DeliverySlotsView, DeliveryZonesView

app_name = "delivery"

urlpatterns = [
    path("zones/", DeliveryZonesView.as_view(), name="zones"),
    path("slots/", DeliverySlotsView.as_view(), name="slots"),
    path("cdek/cities/", CdekCitiesView.as_view(), name="cdek-cities"),
    path("cdek/points/", CdekPointsView.as_view(), name="cdek-points"),
]
