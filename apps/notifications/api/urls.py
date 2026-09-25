"""URL-ы notification domain (#515). Подключаются в config/urls под /api/."""

from django.urls import path

from . import views

app_name = "notifications_api"

urlpatterns = [
    path(
        "account/notifications/preferences/",
        views.NotificationPreferenceView.as_view(),
        name="preferences",
    ),
    path("account/notifications/", views.NotificationListView.as_view(), name="list"),
    path(
        "account/notifications/unread-count/",
        views.NotificationUnreadCountView.as_view(),
        name="unread-count",
    ),
    path(
        "account/notifications/read-all/",
        views.NotificationMarkAllReadView.as_view(),
        name="read-all",
    ),
    path(
        "account/notifications/<int:pk>/read/",
        views.NotificationMarkReadView.as_view(),
        name="mark-read",
    ),
]
