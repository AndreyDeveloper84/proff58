"""Маршруты API для 1С под префиксом /api/1c/."""

from django.urls import path

from . import views

app_name = "sync_1c_api"

urlpatterns = [
    path("snapshot/", views.snapshot, name="snapshot"),
    path("products/import", views.products_import, name="products-import"),
    path("products/update", views.products_update, name="products-update"),
    path("prices/update", views.prices_update, name="prices-update"),
    path("stocks/update", views.stocks_update, name="stocks-update"),
    path("sync/<uuid:batch_uid>", views.sync_status, name="sync-status"),
    path("orders/new", views.orders_new, name="orders-new"),
    path("orders/confirm", views.orders_confirm, name="orders-confirm"),
]
