"""API промокода корзины (#571): POST/DELETE /api/cart/promo/ + breakdown в GET /api/cart/."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.promotions.models import DiscountType, PromoScope, Promotion


def _flags_on(settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "promotions": True}


@pytest.fixture
def sale(db, product):
    promo = Promotion.objects.create(
        name="Скидка на дрель",
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal("10"),
        scope=PromoScope.PRODUCT,
        promo_code="SALE10",
    )
    promo.products.set([product])
    return promo


def _fill_cart(api, product, qty=2):
    resp = api.post("/api/cart/items/", {"product_id": product.id, "quantity": qty}, format="json")
    assert resp.status_code in (200, 201)
    return resp


@pytest.mark.django_db
def test_flag_off_promo_endpoint_hidden_and_fields_neutral(api, product, sale):
    """Выключенный флаг: /api/cart/promo → 404, а GET /api/cart несёт нейтральные поля."""
    _fill_cart(api, product)
    assert api.post("/api/cart/promo/", {"code": "SALE10"}, format="json").status_code == 404
    assert api.delete("/api/cart/promo/").status_code == 404

    data = api.get("/api/cart/").json()
    assert data["promotions_enabled"] is False
    assert data["items_discount_total"] == "0.00"
    assert data["grand_total"] == data["total"]  # нейтрально: без скидок
    assert data["applied_promotions"] == []
    assert data["promo_code"] == "" and data["promo_code_error"] is None


@pytest.mark.django_db
def test_apply_promo_returns_breakdown(api, settings, product, sale):
    _flags_on(settings)
    _fill_cart(api, product, qty=2)  # 2 × 1000

    resp = api.post("/api/cart/promo/", {"code": "sale10"}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["promo_code"] == "SALE10"  # каноническое написание из акции
    assert data["items_discount_total"] == "200.00"
    assert data["grand_total"] == "1800.00"
    assert data["total"] == "2000.00"  # сумма строк до промо — контракт не менялся
    assert data["applied_promotions"][0]["promo_code"] == "SALE10"
    assert data["lines"][0]["promo_discount"] == "200.00"

    # Код живёт на корзине: обычный GET тоже отдаёт скидку (переживёт cart→checkout).
    again = api.get("/api/cart/").json()
    assert again["promo_code"] == "SALE10" and again["grand_total"] == "1800.00"


@pytest.mark.django_db
def test_invalid_code_400_and_not_stored(api, settings, product, sale):
    _flags_on(settings)
    _fill_cart(api, product)
    resp = api.post("/api/cart/promo/", {"code": "NOPE"}, format="json")
    assert resp.status_code == 400
    assert "нет" in resp.json()["detail"]  # «Такого промокода нет.»
    assert api.get("/api/cart/").json()["promo_code"] == ""  # не прилип

    assert api.post("/api/cart/promo/", {"code": ""}, format="json").status_code == 400


@pytest.mark.django_db
def test_remove_promo(api, settings, product, sale):
    _flags_on(settings)
    _fill_cart(api, product)
    api.post("/api/cart/promo/", {"code": "SALE10"}, format="json")
    resp = api.delete("/api/cart/promo/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["promo_code"] == ""
    assert data["items_discount_total"] == "0.00"
    assert data["grand_total"] == data["total"]


@pytest.mark.django_db
def test_code_expired_after_apply_reported_not_silently_kept(api, settings, product, sale):
    """Код истёк ПОСЛЕ применения: GET /api/cart честно отдаёт promo_code_error."""
    _flags_on(settings)
    _fill_cart(api, product)
    api.post("/api/cart/promo/", {"code": "SALE10"}, format="json")
    Promotion.objects.filter(pk=sale.pk).update(
        ends_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    data = api.get("/api/cart/").json()
    assert data["items_discount_total"] == "0.00"
    assert data["promo_code_error"]["code"] == "expired"
    assert "истёк" in data["promo_code_error"]["message"]


@pytest.mark.django_db
def test_auto_promotion_applies_without_code(api, settings, product):
    """Автоакция (без кода) видна в корзине без каких-либо действий пользователя."""
    _flags_on(settings)
    promo = Promotion.objects.create(
        name="Авто −5%",
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal("5"),
        scope=PromoScope.PRODUCT,
    )
    promo.products.set([product])
    _fill_cart(api, product, qty=1)
    data = api.get("/api/cart/").json()
    assert data["items_discount_total"] == "50.00"
    assert data["applied_promotions"][0]["name"] == "Авто −5%"
    assert data["promo_code"] == ""
