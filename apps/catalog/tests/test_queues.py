"""Очереди каталога: счётчик дашборда и фильтр списка должны давать одно и то же.

Смысл apps.catalog.queues — единственное определение «что требует внимания».
Если фильтр админки и карточка стартового экрана посчитают по-разному, человек
увидит «12», откроет и найдёт 8 — и перестанет верить дашборду.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite

from apps.catalog import queues
from apps.catalog.admin import ContentGapFilter, ModerationQueueFilter, ProductAdmin
from apps.catalog.models import Category, Product, ProductImage, ProductStatus


@pytest.fixture
def category(db):
    return Category.add_root(name="Инструмент", slug="instrument")


def _product(name, **kwargs):
    defaults = {
        "slug": name.lower().replace(" ", "-"),
        "code_1c": f"q-{name}",
        "status": ProductStatus.PUBLISHED,
        "price": Decimal("1000.00"),
        "short_description": "текст",
    }
    defaults.update(kwargs)
    return Product.objects.create(name=name, **defaults)


@pytest.fixture
def набор(category):
    """Товары с разными пробелами в заполнении."""
    ok = _product("Полный", category=category)
    ProductImage.objects.create(product=ok, image="products/ok.jpg")
    return {
        "полный": ok,
        "без_категории": _product("Без категории", category=None),
        "без_описания": _product("Без описания", category=category, short_description=""),
        "без_цены": _product("Без цены", category=category, price=None),
        "на_проверке": _product(
            "На проверке", category=category, status=ProductStatus.NEEDS_REVIEW
        ),
    }


def test_без_категории(набор):
    assert list(queues.without_category()) == [набор["без_категории"]]


def test_без_фото_не_включает_товар_с_фото(набор):
    slugs = set(queues.without_image().values_list("slug", flat=True))
    assert набор["полный"].slug not in slugs
    assert набор["без_цены"].slug in slugs


def test_без_описания(набор):
    assert list(queues.without_description()) == [набор["без_описания"]]


def test_без_цены_ловит_и_ноль_и_пусто(набор, category):
    нулевая = _product("Нулевая цена", category=category, price=Decimal("0.00"))
    slugs = set(queues.without_price().values_list("slug", flat=True))
    assert {набор["без_цены"].slug, нулевая.slug} <= slugs
    assert набор["полный"].slug not in slugs


def test_требуют_внимания_не_берёт_опубликованные(набор):
    slugs = set(queues.needs_attention().values_list("slug", flat=True))
    assert набор["на_проверке"].slug in slugs
    assert набор["полный"].slug not in slugs
    assert набор["без_описания"].slug not in slugs  # опубликован → не в очереди


def test_фильтр_админки_и_очередь_считают_одинаково(набор, rf):
    """Главное свойство: за фильтром и за дашбордом один и тот же код."""
    admin_obj = ProductAdmin(Product, AdminSite())
    request = rf.get("/admin/catalog/product/", {"moderation": "attention"})

    filtered = ModerationQueueFilter(
        request, {"moderation": ["attention"]}, Product, admin_obj
    ).queryset(request, Product.objects.all())

    assert set(filtered.values_list("pk", flat=True)) == set(
        queues.needs_attention().values_list("pk", flat=True)
    )


@pytest.mark.parametrize(
    "value,queue",
    [
        ("no_image", queues.without_image),
        ("no_description", queues.without_description),
        ("no_price", queues.without_price),
    ],
)
def test_полки_каталога_совпадают_с_очередями(набор, rf, value, queue):
    admin_obj = ProductAdmin(Product, AdminSite())
    request = rf.get("/admin/catalog/product/", {"content": value})

    filtered = ContentGapFilter(request, {"content": [value]}, Product, admin_obj).queryset(
        request, Product.objects.all()
    )

    assert set(filtered.values_list("pk", flat=True)) == set(queue().values_list("pk", flat=True))
