"""Маршруты тестовой витрины каталога под префиксом ``/catalog/``."""

from django.urls import path, re_path

from . import storefront_views

app_name = "catalog_web"

urlpatterns = [
    path("", storefront_views.catalog_index, name="index"),
    re_path(r"^(?P<slug_path>[\w\-/]+)/$", storefront_views.category_detail, name="category"),
]
