import pytest

from apps.leads.api.serializers import ProductInquirySerializer
from apps.leads.models import InquiryKind


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+7 (999) 000-00-03", "+79990000003"),
        ("8 999 000 00 03", "+79990000003"),
        ("79990000003", "+79990000003"),
    ],
)
def test_phone_is_normalized(product, raw, expected):
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": raw}
    )
    assert s.is_valid(), s.errors
    assert s.validated_data["phone"] == expected


@pytest.mark.django_db
def test_invalid_phone_rejected(product):
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": "123"}
    )
    assert not s.is_valid()
    assert "phone" in s.errors


@pytest.mark.django_db
def test_consultation_valid_without_product():
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.CONSULTATION, "phone": "89990001122", "name": "Иван"}
    )
    assert s.is_valid(), s.errors
    inquiry = s.save()
    assert inquiry.product_id is None
    assert inquiry.phone == "+79990001122"


@pytest.mark.django_db
def test_price_request_requires_product():
    s = ProductInquirySerializer(data={"kind": InquiryKind.PRICE_REQUEST, "phone": "89990001122"})
    assert not s.is_valid()
    assert "product" in s.errors
