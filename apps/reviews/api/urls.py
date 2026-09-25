from django.urls import path, re_path

from . import views

app_name = "reviews_api"

_SLUG = r"(?P<slug>[-\w]+)"  # как в catalog: кириллические slug допустимы

urlpatterns = [
    path("account/reviews/", views.AccountReviewsView.as_view(), name="account-reviews"),
    re_path(
        rf"^reviews/product/{_SLUG}/$", views.ProductReviewsView.as_view(), name="product-reviews"
    ),
]
