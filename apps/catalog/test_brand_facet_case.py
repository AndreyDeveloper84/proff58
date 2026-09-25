"""Бренд-фасет не должен дробиться по регистру (#11 код-ревью).

GROUP BY brand без нормализации регистра выдавал раздельные «Bosch»/«BOSCH»,
а фильтр товаров — brand__iexact (объединяет). Сумма счётчиков фасета ≠ числу
товаров в выдаче. Проверяем, что варианты регистра схлопываются в один фасет.
"""

from decimal import Decimal

import pytest

from apps.catalog.facets import build_facets
from apps.catalog.models import Category, Product, ProductStatus, StockStatus


@pytest.mark.django_db
def test_brand_facet_combines_case_variants():
    root = Category.add_root(name="Электроинструмент", slug="electro-bf")
    leaf = root.add_child(name="Дрели", slug="drills-bf")
    for i, brand in enumerate(["Bosch", "BOSCH"]):
        Product.objects.create(
            category=leaf,
            name=f"p{i}",
            slug=f"brand-case-{i}",
            brand=brand,
            price=Decimal("100.00"),
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_status=StockStatus.IN_STOCK,
        )

    brands = build_facets(leaf)["brands"]
    assert len(brands) == 1, brands
    assert brands[0]["count"] == 2
