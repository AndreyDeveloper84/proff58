from django.urls import path

from . import views

app_name = "accounts_api"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("me/", views.MeView.as_view(), name="me"),
    path("otp-login/", views.OTPLoginView.as_view(), name="otp-login"),
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
]
