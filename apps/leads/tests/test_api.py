import pytest

from apps.leads.models import InquiryKind, ProductInquiry


@pytest.mark.django_db
def test_post_inquiry_creates_201(api, product):
    resp = api.post(
        "/api/leads/inquiries/",
        {"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": "8 999 000 00 04"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert set(resp.data.keys()) == {"id", "kind", "status"}
    assert resp.data["status"] == "new"
    inq = ProductInquiry.objects.get(pk=resp.data["id"])
    assert inq.phone == "+79990000004"


@pytest.mark.django_db
def test_post_inquiry_invalid_phone_400(api, product):
    resp = api.post(
        "/api/leads/inquiries/",
        {"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": "x"},
        format="json",
    )
    assert resp.status_code == 400
    assert "phone" in resp.data


@pytest.mark.django_db
def test_post_consultation_inquiry(api):
    resp = api.post(
        "/api/leads/inquiries/",
        {"kind": "consultation", "phone": "89990001122", "name": "Иван", "message": "подберите"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["kind"] == "consultation"
    assert set(body.keys()) == {"id", "kind", "status"}
