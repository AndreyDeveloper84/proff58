"""Маршруты API заказов и корзины."""

from django.urls import path

from . import views

app_name = "orders_api"

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/promo/", views.CartPromoView.as_view(), name="cart-promo"),
    path("cart/items/", views.CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<int:pk>/", views.CartItemDetailView.as_view(), name="cart-item-detail"),
    path(
        "cart/items/<int:pk>/restore/",
        views.CartItemRestoreView.as_view(),
        name="cart-item-restore",
    ),
    # #560: счета B2B в ЛК. Префикс account/ здесь легален: urls смонтированы на
    # /api/ (как account/max/* у integration_max), а nginx уже шлёт /api/account/
    # целиком в Next-BFF.
    path("account/invoices/", views.AccountInvoicesView.as_view(), name="account-invoices"),
    path(
        "account/invoices/<str:number>/",
        views.AccountInvoiceDetailView.as_view(),
        name="account-invoice-detail",
    ),
    path("orders/", views.OrdersView.as_view(), name="orders"),
    path("orders/<str:number>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:number>/cancel/", views.OrderCancelView.as_view(), name="order-cancel"),
    path("orders/<str:number>/invoice/", views.InvoiceView.as_view(), name="order-invoice"),
    path("orders/<str:number>/guest/", views.GuestOrderView.as_view(), name="guest-order"),
]
