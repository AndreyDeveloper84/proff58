from django.urls import path

from .views import ProductInquiryCreateView

app_name = "leads"

urlpatterns = [
    path("inquiries/", ProductInquiryCreateView.as_view(), name="inquiry-create"),
]
