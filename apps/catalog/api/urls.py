"""Маршруты публичного API каталога под префиксом /api/catalog/."""

from django.urls import path, re_path

from . import views

app_name = "catalog_api"

# \w в Python 3 включает Unicode → кириллические slug работают
_SLUG = r"(?P<slug>[-\w]+)"

urlpatterns = [
    path("categories/", views.CategoryTreeView.as_view(), name="categories"),
    re_path(
        rf"^categories/{_SLUG}/facets/$",
        views.CategoryFacetsView.as_view(),
        name="category-facets",
    ),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("bestsellers/", views.BestsellersView.as_view(), name="bestsellers"),
    path(
        "search/suggest/",
        views.ProductSuggestView.as_view(),
        name="product-suggest",
    ),
    path(
        "search/facets/",
        views.SearchFacetsView.as_view(),
        name="search-facets",
    ),
    re_path(
        rf"^products/{_SLUG}/compatible/$",
        views.ProductCompatibleView.as_view(),
        name="product-compatible",
    ),
    re_path(
        rf"^products/{_SLUG}/availability-subscription/$",
        views.ProductAvailabilitySubscriptionView.as_view(),
        name="product-availability-subscription",
    ),
    re_path(rf"^products/{_SLUG}/$", views.ProductDetailView.as_view(), name="product-detail"),
]
