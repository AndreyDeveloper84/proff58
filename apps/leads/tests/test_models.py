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


@pytest.mark.django_db
def test_consultation_inquiry_has_no_product():
    inquiry = ProductInquiry.objects.create(
        kind=InquiryKind.CONSULTATION, product=None, phone="+79990001122"
    )
    assert inquiry.pk is not None
    assert inquiry.product_id is None
    assert inquiry.kind == "consultation"
    assert str(inquiry)  # __str__ не падает на product=None
