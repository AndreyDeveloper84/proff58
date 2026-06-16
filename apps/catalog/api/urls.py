"""Маршруты публичного API каталога под префиксом /api/catalog/."""

from django.urls import path

from . import views

app_name = "catalog_api"

urlpatterns = [
    path("categories/", views.CategoryTreeView.as_view(), name="categories"),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("products/<slug:slug>/", views.ProductDetailView.as_view(), name="product-detail"),
]
