"""URL-ы API авторизации через MAX (#492). Подключаются в config/urls под /api/."""

from django.urls import path

from . import views

app_name = "integration_max_api"

urlpatterns = [
    path("auth/max/start/", views.MaxAuthStartView.as_view(), name="auth-start"),
    path(
        "auth/max/<uuid:public_id>/status/", views.MaxAuthStatusView.as_view(), name="auth-status"
    ),
    path(
        "auth/max/<uuid:public_id>/cancel/", views.MaxAuthCancelView.as_view(), name="auth-cancel"
    ),
    path("account/max/link/", views.MaxLinkStartView.as_view(), name="account-link"),
    path("account/max/unlink/", views.MaxUnlinkView.as_view(), name="account-unlink"),
    path("account/max/status/", views.MaxStatusMeView.as_view(), name="account-status"),
]
