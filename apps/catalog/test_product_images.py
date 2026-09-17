"""Главное фото товара для корзины и заказов.

Корзина годами показывала вместо фото зашитую картинку-заглушку, потому что фото
до неё просто не доходило. Эта функция — единственный путь фото в чужие модули,
поэтому тесты держат три вещи: выбирается тот же кадр, что в выдаче каталога;
товар без фото не получает выдуманный адрес; сколько бы ни было товаров — один
запрос.
"""

from decimal import Decimal

import pytest

from apps.catalog.models import Product, ProductImage, ProductStatus
from apps.catalog.services import main_image_urls


def make_product(slug):
    return Product.objects.create(
        name=slug,
        slug=slug,
        price=Decimal("100"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


@pytest.mark.django_db
def test_главное_фото_важнее_порядка():
    p = make_product("drel")
    ProductImage.objects.create(product=p, image="products/first.jpg", sort_order=0)
    ProductImage.objects.create(product=p, image="products/main.jpg", sort_order=5, is_main=True)

    assert main_image_urls([p.id]) == {p.id: "/media/products/main.jpg"}


@pytest.mark.django_db
def test_без_главного_берётся_первое_по_порядку():
    p = make_product("pila")
    ProductImage.objects.create(product=p, image="products/second.jpg", sort_order=2)
    ProductImage.objects.create(product=p, image="products/first.jpg", sort_order=1)

    assert main_image_urls([p.id]) == {p.id: "/media/products/first.jpg"}


@pytest.mark.django_db
def test_товар_без_фото_в_ответ_не_попадает():
    with_photo = make_product("s-foto")
    without = make_product("bez-foto")
    ProductImage.objects.create(product=with_photo, image="products/x.jpg", is_main=True)

    urls = main_image_urls([with_photo.id, without.id, None])

    # Отсутствие ключа — сигнал витрине показать «Фото готовится», а не битую картинку.
    assert without.id not in urls
    assert set(urls) == {with_photo.id}


@pytest.mark.django_db
def test_запись_без_файла_пропускается():
    p = make_product("bitoe")
    ProductImage.objects.create(product=p, image="", is_main=True)
    ProductImage.objects.create(product=p, image="products/ok.jpg", sort_order=1)

    assert main_image_urls([p.id]) == {p.id: "/media/products/ok.jpg"}


@pytest.mark.django_db
def test_один_запрос_на_любое_число_товаров(django_assert_num_queries):
    ids = []
    for i in range(5):
        p = make_product(f"t-{i}")
        ProductImage.objects.create(product=p, image=f"products/{i}.jpg", is_main=True)
        ids.append(p.id)

    with django_assert_num_queries(1):
        urls = main_image_urls(ids)

    assert len(urls) == 5


def test_пустой_список_не_ходит_в_базу():
    assert main_image_urls([]) == {}
    assert main_image_urls([None]) == {}
