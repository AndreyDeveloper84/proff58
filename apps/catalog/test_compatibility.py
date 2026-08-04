"""Тесты движка совместимости товаров (#79): модель, резолверы, API, admin."""

import pytest
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.catalog.admin import (
    ProductCompatibilityIncomingInline,
    ProductCompatibilityInline,
)
from apps.catalog.models import (
    Category,
    CompatibilityKind,
    Product,
    ProductCompatibility,
    ProductStatus,
)
from apps.catalog.queries import (
    accessories_of,
    compatibility_sections,
    compatible_of,
    fits_of,
)

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def cat(db):
    return Category.add_root(name="Электроинструмент", slug="ei")


def make_product(category, name, slug, **kw):
    data = {
        "category": category,
        "name": name,
        "slug": slug,
        "status": ProductStatus.PUBLISHED,
        "is_active": True,
        "price": "1000",
    }
    data.update(kw)
    return Product.objects.create(**data)


def link(source, target, kind, **kw):
    return ProductCompatibility.objects.create(source=source, target=target, kind=kind, **kw)


# ---------------------------------------------------------------------------
# Модель: констрейнты и каскад
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unique_constraint_duplicate(cat):
    a = make_product(cat, "A", "a")
    b = make_product(cat, "B", "b")
    link(a, b, CompatibilityKind.ACCESSORY)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            link(a, b, CompatibilityKind.ACCESSORY)


@pytest.mark.django_db
def test_self_link_forbidden(cat):
    a = make_product(cat, "A", "a")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ProductCompatibility.objects.create(
                source=a, target=a, kind=CompatibilityKind.ACCESSORY
            )


@pytest.mark.django_db
def test_delete_product_cascades_edges(cat):
    a = make_product(cat, "A", "a")
    b = make_product(cat, "B", "b")
    link(a, b, CompatibilityKind.ACCESSORY)
    assert ProductCompatibility.objects.count() == 1
    a.delete()
    assert ProductCompatibility.objects.count() == 0


# ---------------------------------------------------------------------------
# Канонизация COMPATIBLE
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_compatible_canonicalized_on_save(cat):
    a = make_product(cat, "A", "a")
    b = make_product(cat, "B", "b")
    assert a.id < b.id
    # Создаём B→A (source.id > target.id) → должно сохраниться как A→B.
    edge = link(b, a, CompatibilityKind.COMPATIBLE)
    edge.refresh_from_db()
    assert edge.source_id == a.id
    assert edge.target_id == b.id


@pytest.mark.django_db
def test_compatible_no_reverse_duplicate(cat):
    a = make_product(cat, "A", "a")
    b = make_product(cat, "B", "b")
    link(a, b, CompatibilityKind.COMPATIBLE)
    # Обратное ребро B→A после канонизации == A→B → ловится unique-констрейнтом.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            link(b, a, CompatibilityKind.COMPATIBLE)
    assert ProductCompatibility.objects.count() == 1


@pytest.mark.django_db
def test_compatible_symmetric_resolvers(cat):
    a = make_product(cat, "A", "a")
    b = make_product(cat, "B", "b")
    link(b, a, CompatibilityKind.COMPATIBLE)  # хранится канонически A→B
    a_items = compatible_of(a)
    b_items = compatible_of(b)
    assert [i.product.id for i in a_items] == [b.id]
    assert [i.product.id for i in b_items] == [a.id]


# ---------------------------------------------------------------------------
# ACCESSORY направленный и НЕ канонизируется
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accessory_not_canonicalized(cat):
    a = make_product(cat, "A", "a")
    b = make_product(cat, "B", "b")
    # A→B и B→A ACCESSORY — два разных ребра (направление значимо).
    link(a, b, CompatibilityKind.ACCESSORY)
    link(b, a, CompatibilityKind.ACCESSORY)
    assert ProductCompatibility.objects.count() == 2
    e1 = ProductCompatibility.objects.get(source=a, target=b)
    e2 = ProductCompatibility.objects.get(source=b, target=a)
    assert e1.id != e2.id


@pytest.mark.django_db
def test_accessory_asymmetric(cat):
    tool = make_product(cat, "Перфоратор", "tool")
    battery = make_product(cat, "Аккумулятор", "battery")
    link(tool, battery, CompatibilityKind.ACCESSORY)

    assert [i.product.id for i in accessories_of(tool)] == [battery.id]
    assert accessories_of(battery) == []
    assert [i.product.id for i in fits_of(battery)] == [tool.id]
    assert fits_of(tool) == []


# ---------------------------------------------------------------------------
# Порядок и видимость
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sort_order(cat):
    tool = make_product(cat, "Инструмент", "tool")
    b1 = make_product(cat, "Акс1", "acc1")
    b2 = make_product(cat, "Акс2", "acc2")
    b3 = make_product(cat, "Акс3", "acc3")
    link(tool, b2, CompatibilityKind.ACCESSORY, sort_order=5)
    link(tool, b1, CompatibilityKind.ACCESSORY, sort_order=1)
    link(tool, b3, CompatibilityKind.ACCESSORY, sort_order=5)  # тай-брейк по id
    ids = [i.product.id for i in accessories_of(tool)]
    assert ids == [b1.id, b2.id, b3.id]


@pytest.mark.django_db
def test_visibility_excludes_hidden_targets(cat):
    tool = make_product(cat, "Инструмент", "tool")
    visible = make_product(cat, "Видимый", "vis")
    draft = make_product(cat, "Черновик", "draft", status=ProductStatus.DRAFT)
    off = make_product(cat, "Выключен", "off", is_active=False)
    for acc in (visible, draft, off):
        link(tool, acc, CompatibilityKind.ACCESSORY)
    assert [i.product.id for i in accessories_of(tool)] == [visible.id]


@pytest.mark.django_db
def test_visibility_excludes_hidden_sources(cat):
    visible_tool = make_product(cat, "Видимый инструмент", "vis-tool")
    draft_tool = make_product(cat, "Черновик инструмент", "draft-tool", status=ProductStatus.DRAFT)
    acc = make_product(cat, "Аксессуар", "acc")
    link(visible_tool, acc, CompatibilityKind.ACCESSORY)
    link(draft_tool, acc, CompatibilityKind.ACCESSORY)
    assert [i.product.id for i in fits_of(acc)] == [visible_tool.id]


@pytest.mark.django_db
def test_compatible_visibility(cat):
    a = make_product(cat, "A", "a")
    hidden = make_product(cat, "Скрытый", "hidden", is_active=False)
    link(a, hidden, CompatibilityKind.COMPATIBLE)
    assert compatible_of(a) == []


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_api_sections(client, cat):
    tool = make_product(cat, "Инструмент", "tool")
    acc = make_product(cat, "Аксессуар", "acc", price="500")
    fitter = make_product(cat, "Подходит к", "fitter")
    compat = make_product(cat, "Совместимый", "compat", price="700")

    link(tool, acc, CompatibilityKind.ACCESSORY, note="идёт в комплект")
    link(fitter, tool, CompatibilityKind.ACCESSORY)  # tool подходит к fitter
    link(tool, compat, CompatibilityKind.COMPATIBLE)

    resp = client.get("/api/catalog/products/tool/compatible/")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {
        "accessories",
        "cross_sell",
        "analogs",
        "fits",
        "compatible",
    }

    assert [r["slug"] for r in data["accessories"]] == ["acc"]
    assert data["accessories"][0]["note"] == "идёт в комплект"
    assert data["accessories"][0]["price"] == "500.00"

    assert [r["slug"] for r in data["fits"]] == ["fitter"]
    assert [r["slug"] for r in data["compatible"]] == ["compat"]
    assert data["compatible"][0]["price"] == "700.00"


@pytest.mark.django_db
def test_api_unknown_slug_404(client, cat):
    assert client.get("/api/catalog/products/nope/compatible/").status_code == 404


@pytest.mark.django_db
def test_api_hidden_slug_404(client, cat):
    make_product(cat, "Черновик", "draft-x", status=ProductStatus.DRAFT)
    assert client.get("/api/catalog/products/draft-x/compatible/").status_code == 404


@pytest.mark.django_db
def test_api_same_product_in_two_sections(client, cat):
    """Один товар может быть и в compatible, и в accessories (дедуп лишь внутри секции)."""
    tool = make_product(cat, "Инструмент", "tool")
    both = make_product(cat, "Универсал", "both")
    link(tool, both, CompatibilityKind.ACCESSORY)
    link(tool, both, CompatibilityKind.COMPATIBLE)

    data = client.get("/api/catalog/products/tool/compatible/").json()
    assert [r["slug"] for r in data["accessories"]] == ["both"]
    assert [r["slug"] for r in data["compatible"]] == ["both"]


@pytest.mark.django_db
def test_api_no_nplus1(client, cat, django_assert_max_num_queries):
    tool = make_product(cat, "Инструмент", "tool")
    for i in range(8):
        acc = make_product(cat, f"Акс {i}", f"acc-{i}")
        link(tool, acc, CompatibilityKind.ACCESSORY, sort_order=i)
    with django_assert_max_num_queries(10):
        resp = client.get("/api/catalog/products/tool/compatible/")
    assert resp.status_code == 200
    assert len(resp.json()["accessories"]) == 8


@pytest.mark.django_db
def test_sections_helper(cat):
    tool = make_product(cat, "Инструмент", "tool")
    acc = make_product(cat, "Аксессуар", "acc")
    link(tool, acc, CompatibilityKind.ACCESSORY)
    sections = compatibility_sections(tool)
    assert set(sections.keys()) == {
        "accessories",
        "cross_sell",
        "analogs",
        "fits",
        "compatible",
    }
    assert [i.product.id for i in sections["accessories"]] == [acc.id]


# ---------------------------------------------------------------------------
# Admin (smoke)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_inlines_registered():
    product_admin = admin_site._registry[Product]
    inline_classes = product_admin.inlines
    assert ProductCompatibilityInline in inline_classes
    assert ProductCompatibilityIncomingInline in inline_classes


@pytest.mark.django_db
def test_admin_incoming_inline_readonly():
    inline = ProductCompatibilityIncomingInline(ProductCompatibility, admin_site)
    assert inline.has_add_permission(None) is False
    assert inline.has_change_permission(None) is False
    assert inline.has_delete_permission(None) is False
