"""Маршруты публичного API каталога под префиксом /api/catalog/."""

from django.urls import path

from . import views

app_name = "catalog_api"

urlpatterns = [
    path("categories/", views.CategoryTreeView.as_view(), name="categories"),
    path(
        "categories/<slug:slug>/facets/",
        views.CategoryFacetsView.as_view(),
        name="category-facets",
    ),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path(
        "search/suggest/",
        views.ProductSuggestView.as_view(),
        name="product-suggest",
    ),
    path(
        "products/<slug:slug>/compatible/",
        views.ProductCompatibleView.as_view(),
        name="product-compatible",
    ),
    path("products/<slug:slug>/", views.ProductDetailView.as_view(), name="product-detail"),
]
