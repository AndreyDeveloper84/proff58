import pytest

from apps.leads.models import InquiryKind, ProductInquiry
from apps.leads.services import create_inquiry


@pytest.mark.django_db
def test_create_inquiry_consultation_without_product():
    inquiry = create_inquiry(
        kind=InquiryKind.CONSULTATION, phone="+79990001122", name="Иван", message="нужна дрель"
    )
    assert inquiry.product_id is None
    assert inquiry.kind == "consultation"
    assert inquiry.name == "Иван"


@pytest.mark.django_db(transaction=True)
def test_create_inquiry_persists_and_emits_event(product):
    received = {}

    from apps.core.events import product_inquiry_created

    def handler(sender, **kwargs):
        received.update(kwargs)

    product_inquiry_created.connect(handler, weak=False)
    try:
        inq = create_inquiry(
            kind=InquiryKind.PRICE_REQUEST,
            product=product,
            phone="+79990000002",
            name="Пётр",
        )
    finally:
        product_inquiry_created.disconnect(handler)

    assert ProductInquiry.objects.filter(pk=inq.pk).exists()
    assert received["inquiry_id"] == inq.pk
    assert received["product_id"] == product.pk
    assert received["kind"] == InquiryKind.PRICE_REQUEST
