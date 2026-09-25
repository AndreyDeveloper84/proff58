"""Кабинет: подключается в config/urls под /api/account/oauth/ (снаружи — через BFF)."""

from django.urls import path

from . import views

app_name = "integration_oauth_account"

urlpatterns = [
    path("", views.OAuthAccountsView.as_view(), name="accounts"),
    path("<str:provider>/link/", views.OAuthLinkView.as_view(), name="link"),
    path("<str:provider>/unlink/", views.OAuthUnlinkView.as_view(), name="unlink"),
]
