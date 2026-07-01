from django.urls import path

from . import views

app_name = "accounts_api"

urlpatterns = [
    path("csrf/", views.CSRFView.as_view(), name="csrf"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("me/", views.MeView.as_view(), name="me"),
    path("otp-login/", views.OTPLoginView.as_view(), name="otp-login"),
    path("change-phone/", views.ChangePhoneView.as_view(), name="change-phone"),
    path("delete/", views.DeleteAccountView.as_view(), name="delete-account"),
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
]
