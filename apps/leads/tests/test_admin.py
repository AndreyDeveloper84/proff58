import pytest
from django.contrib.admin.sites import AdminSite

from apps.leads.admin import ProductInquiryAdmin
from apps.leads.models import InquiryKind, InquiryStatus, ProductInquiry


@pytest.mark.django_db
def test_mark_processed_action(product):
    inq = ProductInquiry.objects.create(
        kind=InquiryKind.PRICE_REQUEST, product=product, phone="+79990000005"
    )
    admin = ProductInquiryAdmin(ProductInquiry, AdminSite())
    admin.mark_processed(request=None, queryset=ProductInquiry.objects.all())
    inq.refresh_from_db()
    assert inq.status == InquiryStatus.PROCESSED
