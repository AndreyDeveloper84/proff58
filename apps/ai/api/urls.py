"""Маршруты публичного API AI-слоя под префиксом /api/ai/."""

from django.urls import path

from . import views

app_name = "ai_api"

urlpatterns = [
    path(
        "products/<slug:slug>/recommendations/",
        views.ProductRecommendationsView.as_view(),
        name="product-recommendations",
    ),
]
