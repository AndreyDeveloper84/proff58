from django.urls import path, re_path

from . import views

app_name = "content_api"

_SLUG = r"(?P<slug>[-\w]+)"  # как в catalog/reviews: кириллические slug допустимы

urlpatterns = [
    path("pages/", views.InfoPageListView.as_view(), name="info-pages"),
    re_path(rf"^pages/{_SLUG}/$", views.InfoPageDetailView.as_view(), name="info-page"),
    path("articles/", views.ArticleListView.as_view(), name="articles"),
    re_path(rf"^articles/{_SLUG}/$", views.ArticleDetailView.as_view(), name="article"),
]
