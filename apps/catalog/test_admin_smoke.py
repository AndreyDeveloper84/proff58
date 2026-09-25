"""Smoke-тесты admin каталога (#18): доступность страниц и контентный сценарий.

Робастность: проверяем status_code + эффект в БД, НЕ парсим jazzmin-HTML. Логику
правила публикации (категория + обязательные характеристики) проверяем как через
admin-POST (где это стабильно), так и напрямую через модель (full_clean /
publication_errors / action) — admin-POST с инлайнами хрупок по ordering.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
)

User = get_user_model()


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_superuser(phone="+79990000018", password="pw")
    c = Client()
    c.force_login(admin)
    return c


def _empty_inline_management(prefixes):
    """Минимальные management-form поля для пустых инлайнов (0 форм)."""
    data = {}
    for prefix in prefixes:
        data[f"{prefix}-TOTAL_FORMS"] = "0"
        data[f"{prefix}-INITIAL_FORMS"] = "0"
        data[f"{prefix}-MIN_NUM_FORMS"] = "0"
        data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
    return data


# Инлайн-префиксы ProductAdmin (порядок inlines в admin.py):
PRODUCT_INLINE_PREFIXES = [
    "images",
    "attribute_values",
    "price_records",
    "compat_out",  # ProductCompatibilityInline (fk_name=source)
    "compat_in",  # ProductCompatibilityIncomingInline (fk_name=target)
]


def _product_post_data(**overrides):
    """Базовый POST-словарь формы товара с пустыми инлайнами."""
    data = {
        "name": "Товар",
        "slug": "tovar-smoke",
        "status": ProductStatus.DRAFT,
        "article": "",
        "barcode": "",
        "unit": "",
        "brand": "",
        "short_description": "",
        "description": "",
        "currency": "RUB",
        "stock_quantity": "0",
        "reserved_quantity": "0",
        "available_quantity": "0",
        "stock_status": "out_of_stock",
        "meta_title": "",
        "meta_description": "",
        "category": "",
        "_save": "Сохранить",
    }
    data.update(_empty_inline_management(PRODUCT_INLINE_PREFIXES))
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Product: доступность страниц changelist / add / change
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_product_changelist_variations_200(admin_client):
    cat = Category.add_root(name="Инструменты", slug="instr-cl")
    Product.objects.create(name="Дрель", slug="drill-cl", category=cat)
    for url in (
        "/admin/catalog/product/",
        "/admin/catalog/product/?status=published",
        "/admin/catalog/product/?categorized=no",
        "/admin/catalog/product/?q=Дрель",
    ):
        resp = admin_client.get(url)
        assert resp.status_code == 200, url


@pytest.mark.django_db
def test_product_add_and_change_get_200(admin_client):
    p = Product.objects.create(name="Дрель", slug="drill-ac")
    assert admin_client.get("/admin/catalog/product/add/").status_code == 200
    assert admin_client.get(f"/admin/catalog/product/{p.pk}/change/").status_code == 200


@pytest.mark.django_db
def test_product_add_minimal_draft_creates(admin_client):
    resp = admin_client.post(
        "/admin/catalog/product/add/",
        _product_post_data(name="Новый", slug="novyy-draft", status=ProductStatus.DRAFT),
    )
    assert resp.status_code == 302
    p = Product.objects.get(slug="novyy-draft")
    assert p.status == ProductStatus.DRAFT
    assert p.is_active is False


@pytest.mark.django_db
def test_product_change_draft_redirects(admin_client):
    p = Product.objects.create(name="Дрель", slug="drill-chg", status=ProductStatus.DRAFT)
    resp = admin_client.post(
        f"/admin/catalog/product/{p.pk}/change/",
        _product_post_data(name="Дрель-2", slug="drill-chg", status=ProductStatus.DRAFT),
    )
    assert resp.status_code == 302
    p.refresh_from_db()
    assert p.name == "Дрель-2"


# ---------------------------------------------------------------------------
# Category / Attribute: доступность
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_pages(admin_client):
    cat = Category.add_root(name="Категория", slug="cat-pages")
    assert admin_client.get("/admin/catalog/category/").status_code == 200
    assert admin_client.get("/admin/catalog/category/add/").status_code == 200
    assert admin_client.get(f"/admin/catalog/category/{cat.pk}/change/").status_code == 200
    resp = admin_client.post(
        "/admin/catalog/category/add/",
        {
            "name": "Новая",
            "slug": "novaya-cat",
            "description": "",
            "is_active": "on",
            "on_site": "on",
            "sort_order": "0",
            "meta_title": "",
            "meta_description": "",
            "_position": "sorted-sibling",
            "_ref_node_id": "",
            "category_attributes-TOTAL_FORMS": "0",
            "category_attributes-INITIAL_FORMS": "0",
            "category_attributes-MIN_NUM_FORMS": "0",
            "category_attributes-MAX_NUM_FORMS": "1000",
            "_save": "Сохранить",
        },
    )
    assert resp.status_code == 302
    assert Category.objects.filter(slug="novaya-cat").exists()


@pytest.mark.django_db
def test_attribute_pages(admin_client):
    attr = Attribute.objects.create(
        slug="attr-page", name="Атрибут", attribute_type=AttributeType.TEXT
    )
    assert admin_client.get("/admin/catalog/attribute/").status_code == 200
    assert admin_client.get("/admin/catalog/attribute/add/").status_code == 200
    assert admin_client.get(f"/admin/catalog/attribute/{attr.pk}/change/").status_code == 200
    resp = admin_client.post(
        "/admin/catalog/attribute/add/",
        {
            "slug": "novyy-attr",
            "name": "Новый атрибут",
            "attribute_type": AttributeType.TEXT,
            "unit": "",
            "options-TOTAL_FORMS": "0",
            "options-INITIAL_FORMS": "0",
            "options-MIN_NUM_FORMS": "0",
            "options-MAX_NUM_FORMS": "1000",
            "_save": "Сохранить",
        },
    )
    assert resp.status_code == 302
    assert Attribute.objects.filter(slug="novyy-attr").exists()


# ---------------------------------------------------------------------------
# Правило публикации: существующий товар (clean через admin-форму)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publish_existing_blocked_without_required_attr(admin_client):
    cat = Category.add_root(name="Дрели", slug="drills-pub")
    attr = Attribute.objects.create(
        slug="power-pub", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)
    p = Product.objects.create(
        name="Дрель", slug="drill-pub", category=cat, status=ProductStatus.DRAFT
    )

    # Попытка опубликовать через admin без значения обязательного атрибута:
    resp = admin_client.post(
        f"/admin/catalog/product/{p.pk}/change/",
        _product_post_data(
            name="Дрель",
            slug="drill-pub",
            status=ProductStatus.PUBLISHED,
            category=str(cat.pk),
        ),
    )
    # Форма не проходит: код 200 без редиректа, товар в БД не опубликован.
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.status != ProductStatus.PUBLISHED

    # Заполняем атрибут → публикация проходит.
    ProductAttributeValue.objects.create(product=p, attribute=attr, value_integer=600)
    resp = admin_client.post(
        f"/admin/catalog/product/{p.pk}/change/",
        {
            **_product_post_data(
                name="Дрель",
                slug="drill-pub",
                status=ProductStatus.PUBLISHED,
                category=str(cat.pk),
            ),
            "attribute_values-TOTAL_FORMS": "1",
            "attribute_values-INITIAL_FORMS": "1",
            "attribute_values-0-id": str(p.attribute_values.first().pk),
            "attribute_values-0-product": str(p.pk),
            "attribute_values-0-attribute": str(attr.pk),
            "attribute_values-0-value_integer": "600",
            "attribute_values-0-value_text": "",
            "attribute_values-0-source": "manual",
            "attribute_values-0-confidence": "100",
        },
    )
    assert resp.status_code == 302
    p.refresh_from_db()
    assert p.status == ProductStatus.PUBLISHED


@pytest.mark.django_db
def test_same_product_saves_as_draft(admin_client):
    cat = Category.add_root(name="Дрели2", slug="drills-draft")
    attr = Attribute.objects.create(
        slug="power-draft", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)
    p = Product.objects.create(
        name="Дрель", slug="drill-draft", category=cat, status=ProductStatus.PUBLISHED
    )
    resp = admin_client.post(
        f"/admin/catalog/product/{p.pk}/change/",
        _product_post_data(
            name="Дрель",
            slug="drill-draft",
            status=ProductStatus.DRAFT,
            category=str(cat.pk),
        ),
    )
    # Draft без обязательного атрибута — сохраняется свободно.
    assert resp.status_code == 302
    p.refresh_from_db()
    assert p.status == ProductStatus.DRAFT


# ---------------------------------------------------------------------------
# Правило публикации: новый товар через save_related safe-fallback
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publish_new_product_fallback_to_needs_review(admin_client):
    cat = Category.add_root(name="Пилы", slug="saws-new")
    attr = Attribute.objects.create(
        slug="power-new", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)

    resp = admin_client.post(
        "/admin/catalog/product/add/",
        _product_post_data(
            name="Пила",
            slug="saw-new",
            status=ProductStatus.PUBLISHED,
            category=str(cat.pk),
        ),
    )
    # Новый товар: форма сохраняется (302), но save_related откатывает публикацию.
    assert resp.status_code == 302
    p = Product.objects.get(slug="saw-new")
    assert p.status == ProductStatus.NEEDS_REVIEW
    assert p.is_active is False


# ---------------------------------------------------------------------------
# publication_errors / missing_required_attributes: прямые проверки модели
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_required_boolean_false_counts_as_filled():
    cat = Category.add_root(name="Булево", slug="bool-cat")
    attr = Attribute.objects.create(
        slug="has-case", name="В кейсе", attribute_type=AttributeType.BOOLEAN
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)
    p = Product.objects.create(name="Товар", slug="bool-prod", category=cat)
    ProductAttributeValue.objects.create(product=p, attribute=attr, value_boolean=False)

    # boolean False — валидное заполненное значение.
    assert p.missing_required_attributes() == []
    assert p.publication_errors() == []
    # full_clean при PUBLISHED не должен бросать.
    p.status = ProductStatus.PUBLISHED
    p.full_clean()  # не должно поднять ValidationError


@pytest.mark.django_db
def test_publication_errors_no_category():
    p = Product.objects.create(name="Без категории", slug="no-cat")
    assert p.missing_required_attributes() == []
    assert p.publication_errors() == ["Укажите категорию"]


@pytest.mark.django_db
def test_clean_raises_on_publish_with_missing():
    cat = Category.add_root(name="C", slug="clean-cat")
    attr = Attribute.objects.create(
        slug="clean-attr", name="Хар-ка", attribute_type=AttributeType.TEXT
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)
    p = Product.objects.create(
        name="T", slug="clean-prod", category=cat, status=ProductStatus.PUBLISHED
    )
    with pytest.raises(ValidationError):
        p.full_clean()


# ---------------------------------------------------------------------------
# action_publish: bulk с валидным + невалидным
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_action_publish_skips_invalid():
    cat = Category.add_root(name="Bulk", slug="bulk-cat")
    attr = Attribute.objects.create(
        slug="bulk-attr", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)

    valid = Product.objects.create(
        name="Валидный", slug="bulk-valid", category=cat, status=ProductStatus.DRAFT
    )
    ProductAttributeValue.objects.create(product=valid, attribute=attr, value_integer=500)
    invalid = Product.objects.create(
        name="Невалидный", slug="bulk-invalid", category=cat, status=ProductStatus.DRAFT
    )

    admin_obj = ProductAdmin(Product, AdminSite())
    request = RequestFactory().post("/admin/catalog/product/")
    # message_user требует messages-framework на request; подменяем сбор сообщений.
    messages_log = []
    request._messages = type(
        "M", (), {"add": lambda self, level, msg, extra_tags="": messages_log.append(msg)}
    )()

    qs = Product.objects.filter(pk__in=[valid.pk, invalid.pk])
    admin_obj.action_publish(request, qs)

    valid.refresh_from_db()
    invalid.refresh_from_db()
    assert valid.status == ProductStatus.PUBLISHED
    assert valid.is_active is True
    assert invalid.status == ProductStatus.DRAFT
    assert any("Опубликовано" in m and "пропущено" in m for m in messages_log)


# ---------------------------------------------------------------------------
# readonly: code_1c нельзя изменить через admin-POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_code_1c_is_readonly(admin_client):
    p = Product.objects.create(name="Товар", slug="ro-prod", code_1c="ORIG-1C")
    resp = admin_client.post(
        f"/admin/catalog/product/{p.pk}/change/",
        _product_post_data(
            name="Товар",
            slug="ro-prod",
            status=ProductStatus.DRAFT,
            code_1c="HACKED-1C",
        ),
    )
    assert resp.status_code == 302
    p.refresh_from_db()
    assert p.code_1c == "ORIG-1C"


# ---------------------------------------------------------------------------
# action_rebuild_attrs_cache
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_action_rebuild_attrs_cache():
    cat = Category.add_root(name="Cache", slug="cache-cat")
    attr = Attribute.objects.create(
        slug="cache-attr", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    p = Product.objects.create(name="Товар", slug="cache-prod", category=cat)
    ProductAttributeValue.objects.create(product=p, attribute=attr, value_integer=750)

    # Обнуляем кэш, проверяем пересборку.
    Product.objects.filter(pk=p.pk).update(attrs_cache={})
    p.refresh_from_db()
    assert p.attrs_cache == {}

    admin_obj = ProductAdmin(Product, AdminSite())
    request = RequestFactory().post("/admin/catalog/product/")
    request._messages = type("M", (), {"add": lambda *a, **k: None})()

    admin_obj.action_rebuild_attrs_cache(request, Product.objects.filter(pk=p.pk))
    p.refresh_from_db()
    assert p.attrs_cache == {"cache-attr": 750}
