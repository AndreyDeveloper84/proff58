import pytest

from apps.leads.models import InquiryKind, InquiryStatus, ProductInquiry


@pytest.mark.django_db
def test_inquiry_defaults_to_new_status(product):
    inq = ProductInquiry.objects.create(
        kind=InquiryKind.PRICE_REQUEST, product=product, phone="+79990000001"
    )
    assert inq.status == InquiryStatus.NEW
    assert inq.created_at is not None
    assert inq.product.inquiries.count() == 1
