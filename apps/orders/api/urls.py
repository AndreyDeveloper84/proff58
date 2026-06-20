"""Маршруты API заказов и корзины."""

from django.urls import path

from . import views

app_name = "orders_api"

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/items/", views.CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<int:pk>/", views.CartItemDetailView.as_view(), name="cart-item-detail"),
    path("orders/", views.OrdersView.as_view(), name="orders"),
    path("orders/<str:number>/", views.OrderDetailView.as_view(), name="order-detail"),
]
