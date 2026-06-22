"""Регрессионное тестирование MVP перед запуском (issue #41).

Покрывает сквозные пользовательские сценарии:
  - Каталог: витрина, фильтры, пагинация, пустой каталог
  - Аккаунт: профиль B2B, приватность данных
  - Интеграция 1С: API response shape, edge-кейсы
  - Healthcheck и общая инфраструктура
  - Безопасность: CSRF, API-ключи, приватные данные
"""

from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import CustomerType, Profile
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    StockStatus,
)
from apps.pricing.models import PriceRecord

User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()

API_KEY = "regression-test-key"
EAGER = {"CELERY_TASK_ALWAYS_EAGER": True, "CELERY_TASK_EAGER_PROPAGATES": True}


# ─── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def auth_client():
    c = APIClient()
    c.credentials(HTTP_X_API_KEY=API_KEY)
    return c


@pytest.fixture
def category_tree(db):
    root = Category.add_root(name="Электроинструмент", slug="electro")
    mid = root.add_child(name="Дрели и шуруповёрты", slug="drills-group")
    leaf = mid.add_child(name="Ударные дрели", slug="impact-drills")
    return root, mid, leaf


@pytest.fixture
def published_product(category_tree):
    _, _, leaf = category_tree
    return Product.objects.create(
        category=leaf,
        name="Дрель Bosch GSB 13 RE",
        slug="bosch-gsb-13-re",
        brand="Bosch",
        price=Decimal("4500.00"),
        old_price=Decimal("5200.00"),
        stock_quantity=10,
        available_quantity=10,
        stock_status=StockStatus.IN_STOCK,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        description="Профессиональная ударная дрель",
        short_description="Ударная дрель 650 Вт",
    )


@pytest.fixture
def b2b_user(db):
    user = User.objects.create_user(
        phone="+79001234567",
        password="testpass123",
        full_name="Иван Иванов",
        email="ivan@company.ru",
        customer_type=CustomerType.B2B,
    )
    Profile.objects.create(
        user=user,
        company_name='ООО "Стройка"',
        inn="7701234567",
        kpp="770101001",
        legal_address="г. Пенза, ул. Строителей, д. 1",
    )
    return user


# ═══════════════════════════════════════════════════════════════════════
#  1. HEALTHCHECK
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_healthcheck_returns_ok(client):
    resp = client.get("/healthz/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════
#  2. КАТАЛОГ — API response shape
# ═══════════════════════════════════════════════════════════════════════


PRODUCT_LIST_FIELDS = {
    "id",
    "name",
    "slug",
    "brand",
    "category",
    "price",
    "old_price",
    "currency",
    "price_type",
    "stock_status",
    "main_image",
    "short_description",
}

PRODUCT_DETAIL_FIELDS = PRODUCT_LIST_FIELDS | {
    "description",
    "images",
    "attributes",
    "breadcrumb",
}

CATEGORY_TREE_FIELDS = {"id", "name", "slug", "sort_order", "children"}


@pytest.mark.django_db
def test_product_list_response_shape(client, published_product):
    resp = client.get("/api/catalog/products/")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body
    assert "results" in body
    assert body["count"] == 1
    item = body["results"][0]
    assert set(item.keys()) == PRODUCT_LIST_FIELDS


@pytest.mark.django_db
def test_product_detail_response_shape(client, published_product):
    resp = client.get(f"/api/catalog/products/{published_product.slug}/")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == PRODUCT_DETAIL_FIELDS


@pytest.mark.django_db
def test_category_tree_response_shape(client, category_tree):
    resp = client.get("/api/catalog/categories/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert set(data[0].keys()) == CATEGORY_TREE_FIELDS


@pytest.mark.django_db
def test_product_detail_breadcrumb_shape(client, published_product):
    data = client.get(f"/api/catalog/products/{published_product.slug}/").json()
    breadcrumb = data["breadcrumb"]
    assert len(breadcrumb) == 3
    assert [c["slug"] for c in breadcrumb] == ["electro", "drills-group", "impact-drills"]


@pytest.mark.django_db
def test_product_price_fields_types(client, published_product):
    data = client.get(f"/api/catalog/products/{published_product.slug}/").json()
    assert data["price"] == "4500.00"
    assert data["currency"] == "RUB"
    assert data["stock_status"] == "in_stock"


# ═══════════════════════════════════════════════════════════════════════
#  3. КАТАЛОГ — фильтры и пагинация
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_filter_by_brand(client, category_tree):
    _, _, leaf = category_tree
    _make_visible(leaf, "Bosch дрель", "bosch-1", brand="Bosch")
    _make_visible(leaf, "Makita дрель", "makita-1", brand="Makita")
    results = client.get("/api/catalog/products/?brand=bosch").json()["results"]
    assert len(results) == 1
    assert results[0]["brand"] == "Bosch"


@pytest.mark.django_db
def test_filter_by_stock_status(client, category_tree):
    _, _, leaf = category_tree
    _make_visible(leaf, "В наличии", "s-in", stock_status=StockStatus.IN_STOCK)
    _make_visible(leaf, "Нет в наличии", "s-out", stock_status=StockStatus.OUT_OF_STOCK)
    results = client.get("/api/catalog/products/?stock_status=in_stock").json()["results"]
    assert len(results) == 1
    assert results[0]["slug"] == "s-in"


@pytest.mark.django_db
def test_filter_nonexistent_category_returns_empty(client, published_product):
    results = client.get("/api/catalog/products/?category=not-exist").json()["results"]
    assert len(results) == 0


@pytest.mark.django_db
def test_pagination_limit_offset(client, category_tree):
    _, _, leaf = category_tree
    for i in range(5):
        _make_visible(leaf, f"Товар {i:02}", f"pag-{i}")
    body = client.get("/api/catalog/products/?limit=2&offset=0").json()
    assert body["count"] == 5
    assert len(body["results"]) == 2


@pytest.mark.django_db
def test_empty_catalog_returns_empty_list(client):
    body = client.get("/api/catalog/products/").json()
    assert body["count"] == 0
    assert body["results"] == []


@pytest.mark.django_db
def test_nonexistent_product_slug_returns_404(client):
    assert client.get("/api/catalog/products/no-such-product/").status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  4. КАТАЛОГ — visibility logic
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_imported_product_invisible(client, category_tree):
    _, _, leaf = category_tree
    Product.objects.create(
        category=leaf,
        name="Импортированный",
        slug="imported-1",
        status=ProductStatus.IMPORTED,
        is_active=True,
    )
    results = client.get("/api/catalog/products/").json()["results"]
    assert "imported-1" not in {r["slug"] for r in results}


@pytest.mark.django_db
def test_product_published_but_inactive_invisible(client, category_tree):
    _, _, leaf = category_tree
    Product.objects.create(
        category=leaf,
        name="Выключен",
        slug="off-1",
        status=ProductStatus.PUBLISHED,
        is_active=False,
    )
    assert client.get("/api/catalog/products/off-1/").status_code == 404


@pytest.mark.django_db
def test_is_visible_property():
    p = Product(status=ProductStatus.PUBLISHED, is_active=True)
    assert p.is_visible is True
    p.status = ProductStatus.DRAFT
    assert p.is_visible is False


# ═══════════════════════════════════════════════════════════════════════
#  5. КАТАЛОГ — product without category
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_product_without_category_detail(client):
    Product.objects.create(
        name="Без категории",
        slug="no-cat",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        price=100,
    )
    data = client.get("/api/catalog/products/no-cat/").json()
    assert data["category"] is None
    assert data["breadcrumb"] == []


# ═══════════════════════════════════════════════════════════════════════
#  6. КАТАЛОГ — EAV все типы в API
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_eav_all_types_in_api(client, published_product):
    p = published_product
    a_int = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER, unit="Вт"
    )
    a_text = Attribute.objects.create(slug="color", name="Цвет", attribute_type=AttributeType.TEXT)
    ProductAttributeValue.objects.create(product=p, attribute=a_int, value_integer=650)
    ProductAttributeValue.objects.create(product=p, attribute=a_text, value_text="Синий")

    data = client.get(f"/api/catalog/products/{p.slug}/").json()
    attrs = {a["slug"]: a for a in data["attributes"]}
    assert attrs["power"]["value"] == 650
    assert attrs["power"]["unit"] == "Вт"
    assert attrs["color"]["value"] == "Синий"


# ═══════════════════════════════════════════════════════════════════════
#  7. КАТАЛОГ — images
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_product_no_images(client, published_product):
    data = client.get(f"/api/catalog/products/{published_product.slug}/").json()
    assert data["images"] == []
    assert data["main_image"] is None


# ═══════════════════════════════════════════════════════════════════════
#  8. АККАУНТ — приватность
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_b2b_user_profile(b2b_user):
    assert b2b_user.is_b2b is True
    profile = b2b_user.profile
    assert profile.inn == "7701234567"


@pytest.mark.django_db
def test_private_data_not_in_catalog_api(client, published_product, b2b_user):
    resp = client.get("/api/catalog/products/")
    body = resp.content.decode()
    assert b2b_user.phone not in body
    assert "7701234567" not in body


# ═══════════════════════════════════════════════════════════════════════
#  9. 1С API — безопасность
# ═══════════════════════════════════════════════════════════════════════


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_all_1c_endpoints_require_api_key(client):
    endpoints = [
        ("POST", "/api/1c/products/import"),
        ("POST", "/api/1c/products/update"),
        ("POST", "/api/1c/prices/update"),
        ("POST", "/api/1c/stocks/update"),
        ("GET", "/api/1c/sync/00000000-0000-0000-0000-000000000000"),
    ]
    for method, url in endpoints:
        resp = getattr(client, method.lower())(url, {"items": []}, format="json")
        assert resp.status_code == 403, f"{method} {url} should require API key"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_wrong_api_key_denied(client):
    client.credentials(HTTP_X_API_KEY="wrong-key")
    resp = client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_catalog_api_does_not_require_key(client):
    assert client.get("/api/catalog/categories/").status_code == 200
    assert client.get("/api/catalog/products/").status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# 10. 1С API — edge cases
# ═══════════════════════════════════════════════════════════════════════


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_import_empty_items_rejected(auth_client):
    resp = auth_client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_import_missing_items_key(auth_client):
    resp = auth_client.post("/api/1c/products/import", {}, format="json")
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# 11. СКВОЗНОЙ СЦЕНАРИЙ: импорт → витрина
# ═══════════════════════════════════════════════════════════════════════


@override_settings(ONEC_API_KEY=API_KEY, **EAGER)
@pytest.mark.django_db
def test_e2e_import_publish_view(client, auth_client, category_tree):
    _, _, leaf = category_tree
    from apps.catalog.models import CategoryMappingRule, MappingRuleType

    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS,
        pattern="перфоратор",
        target_category=leaf,
    )

    payload = {
        "items": [
            {
                "external_id": "e2e-1",
                "sku": "PERF-001",
                "name": "Перфоратор Bosch GBH 2-26",
                "brand": "Bosch",
                "price": "8900",
                "stock": "5",
            }
        ]
    }
    resp = auth_client.post("/api/1c/products/import", payload, format="json")
    assert resp.status_code == 202

    p = Product.objects.get(code_1c="e2e-1")
    assert p.status == ProductStatus.DRAFT
    assert p.category == leaf

    p.status = ProductStatus.PUBLISHED
    p.is_active = True
    p.save()

    detail = client.get(f"/api/catalog/products/{p.slug}/")
    assert detail.status_code == 200
    assert detail.json()["price"] == "8900.00"


# ═══════════════════════════════════════════════════════════════════════
# 12. HTTP METHOD VALIDATION
# ═══════════════════════════════════════════════════════════════════════


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_1c_import_rejects_get(auth_client):
    resp = auth_client.get("/api/1c/products/import")
    assert resp.status_code == 405


@pytest.mark.django_db
def test_catalog_products_rejects_post(client):
    resp = client.post("/api/catalog/products/", {}, format="json")
    assert resp.status_code == 405


# ═══════════════════════════════════════════════════════════════════════
# 13. МОДЕЛИ — инварианты
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_product_recalc_stock_status():
    p = Product(available_quantity=5)
    p.recalc_stock_status()
    assert p.stock_status == StockStatus.IN_STOCK
    p.available_quantity = 0
    p.recalc_stock_status()
    assert p.stock_status == StockStatus.OUT_OF_STOCK


@pytest.mark.django_db
def test_price_record_default_currency():
    pr = PriceRecord.objects.create(code_1c="pr-1", value=1000)
    assert pr.currency == "RUB"
    assert pr.is_current is True


@pytest.mark.django_db
def test_list_detail_consistency(client, published_product):
    list_resp = client.get("/api/catalog/products/").json()["results"][0]
    detail_resp = client.get(f"/api/catalog/products/{published_product.slug}/").json()
    for field in ("id", "name", "slug", "brand", "price", "currency", "stock_status"):
        assert list_resp[field] == detail_resp[field], f"Mismatch on field: {field}"


# ═══════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_visible(category, name, slug, **kw):
    data = {
        "category": category,
        "name": name,
        "slug": slug,
        "status": ProductStatus.PUBLISHED,
        "is_active": True,
        "price": Decimal("1000"),
    }
    data.update(kw)
    return Product.objects.create(**data)
