"""Маршруты API заказов и корзины."""

from django.urls import path

from . import views

app_name = "orders_api"

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/items/", views.CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<int:pk>/", views.CartItemDetailView.as_view(), name="cart-item-detail"),
    path(
        "cart/items/<int:pk>/restore/",
        views.CartItemRestoreView.as_view(),
        name="cart-item-restore",
    ),
    path("orders/", views.OrdersView.as_view(), name="orders"),
    path("orders/<str:number>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:number>/invoice/", views.InvoiceView.as_view(), name="order-invoice"),
    path("orders/<str:number>/guest/", views.GuestOrderView.as_view(), name="guest-order"),
]
