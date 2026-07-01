"""Серверная сортировка PLP по ЭФФЕКТИВНОЙ цене (P-полировка).

Для B2B (+фича b2b) `?sort=price_*` упорядочивает по опт-цене (PriceRecord wholesale),
для B2C/анонима — по Product.price (retail). Логика совпадает с pricing.services.price_for.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Profile, User
from apps.catalog.models import Category, Product, ProductStatus, StockStatus
from apps.pricing.models import PriceRecord
from apps.pricing.services import WHOLESALE, price_map_for_products


@pytest.fixture
def leaf(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    return root.add_child(name="Дрели", slug="dreli")


@pytest.fixture
def b2b_user(db):
    user = User.objects.create_user(phone="+79990000111", customer_type="b2b")
    Profile.objects.create(user=user, is_b2b_verified=True)
    return user


def make_product(leaf, slug, *, code_1c, price, currency="RUB"):
    return Product.objects.create(
        category=leaf,
        name=slug,
        slug=slug,
        code_1c=code_1c,
        price=price,
        currency=currency,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=StockStatus.IN_STOCK,
    )


def add_wholesale(code_1c, value, currency="RUB"):
    PriceRecord.objects.create(
        code_1c=code_1c, price_type=WHOLESALE, value=value, currency=currency, is_current=True
    )


def order(client, qs="category=dreli&sort=price_asc"):
    return [r["slug"] for r in client.get(f"/api/catalog/products/?{qs}").json()["results"]]


def setup_three(leaf):
    """a: retail100/опт300, b: retail400/опт200, c: retail250/без опта."""
    make_product(leaf, "a", code_1c="A", price=100)
    make_product(leaf, "b", code_1c="B", price=400)
    make_product(leaf, "c", code_1c="C", price=250)
    add_wholesale("A", 300)
    add_wholesale("B", 200)


@pytest.mark.django_db
def test_b2b_sorts_by_effective_wholesale(leaf, b2b_user):
    setup_three(leaf)
    client = APIClient()
    client.force_authenticate(b2b_user)
    # эффективные: b=200, c=250 (без опта→retail), a=300
    assert order(client) == ["b", "c", "a"]


@pytest.mark.django_db
def test_b2c_anon_sorts_by_retail(leaf):
    setup_three(leaf)
    # аноним: по Product.price — a=100, c=250, b=400
    assert order(APIClient()) == ["a", "c", "b"]


@pytest.mark.django_db
@override_settings(FEATURES={"b2b": False})
def test_b2b_feature_off_sorts_by_retail(leaf, b2b_user):
    setup_three(leaf)
    client = APIClient()
    client.force_authenticate(b2b_user)
    assert order(client) == ["a", "c", "b"]  # фича off → retail даже для B2B


@pytest.mark.django_db
def test_b2b_without_wholesale_falls_back_to_retail(leaf, b2b_user):
    make_product(leaf, "cheap", code_1c="X", price=50)  # без опта → effective 50
    make_product(leaf, "pricey", code_1c="Y", price=900)
    add_wholesale("Y", 700)  # effective 700
    client = APIClient()
    client.force_authenticate(b2b_user)
    assert order(client) == ["cheap", "pricey"]  # 50 < 700


@pytest.mark.django_db
def test_nulls_last(leaf, b2b_user):
    make_product(leaf, "withprice", code_1c="P", price=100)
    make_product(leaf, "noprice", code_1c="N", price=None)  # ни retail, ни опт
    client = APIClient()
    client.force_authenticate(b2b_user)
    assert order(client) == ["withprice", "noprice"]  # без цены — в конец
    assert order(client, "category=dreli&sort=price_desc") == ["withprice", "noprice"]


@pytest.mark.django_db
def test_b2b_order_matches_price_map_final(leaf, b2b_user):
    """Инвариант: порядок price_asc совпадает с final-ценами из price_map (не расходится с карточкой)."""
    setup_three(leaf)
    client = APIClient()
    client.force_authenticate(b2b_user)
    prods = list(Product.objects.filter(slug__in=["a", "b", "c"]))
    pm = price_map_for_products(prods, b2b_user)
    expected = [p.slug for p in sorted(prods, key=lambda p: pm[p.pk].final)]
    assert order(client) == expected


@pytest.mark.django_db
def test_search_overrides_sort(leaf, b2b_user):
    setup_three(leaf)
    client = APIClient()
    client.force_authenticate(b2b_user)
    # при поиске сортировка по цене игнорируется (релевантность); запрос не падает
    resp = client.get("/api/catalog/products/?category=dreli&sort=price_asc&search=a")
    assert resp.status_code == 200
