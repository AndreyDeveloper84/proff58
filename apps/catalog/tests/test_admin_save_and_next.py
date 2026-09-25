"""Кнопка «Сохранить и следующий →» в карточке товара.

Нужна для потоковой правки: человек правит товар за товаром и не возвращается
каждый раз в список. Внутри очереди разбора ведёт по очереди, вне её — просто
к следующему товару.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.catalog import moderation
from apps.catalog.models import Category, Product, ProductStatus

User = get_user_model()


@pytest.fixture
def редактор(db):
    return User.objects.create_superuser(phone="+79998880000", password="pwd12345")


@pytest.fixture
def категория(db):
    return Category.add_root(name="Инструмент", slug="instr-next")


def _product(name, **kwargs):
    defaults = {
        "slug": name,
        "code_1c": f"n-{name}",
        "status": ProductStatus.IMPORTED,
        "price": Decimal("1000.00"),
    }
    defaults.update(kwargs)
    return Product.objects.create(name=name, **defaults)


def test_в_очереди_ведёт_по_очереди(db, категория):
    первый = _product("a")
    _product("b", category=категория, status=ProductStatus.PUBLISHED, is_active=True)
    третий = _product("c")

    # b опубликован и в очередь не входит — следующим должен стать c
    assert moderation.next_after(первый).pk == третий.pk


def test_вне_очереди_идёт_по_номеру(db, категория):
    опубликованный = _product(
        "a", category=категория, status=ProductStatus.PUBLISHED, is_active=True
    )
    следующий = _product("b")

    assert moderation.next_after(опубликованный).pk == следующий.pk


def test_последний_товар_даёт_none(db, категория):
    последний = _product("z", category=категория, status=ProductStatus.PUBLISHED, is_active=True)

    assert moderation.next_after(последний) is None


def test_кнопка_есть_в_карточке(client, редактор, db):
    товар = _product("a")
    client.force_login(редактор)

    body = client.get(f"/admin/catalog/product/{товар.pk}/change/").content.decode()

    assert "_save_and_next" in body
    assert "Сохранить и следующий" in body


def test_кнопка_сохраняет_и_ведёт_к_следующему(client, редактор, db):
    первый, второй = _product("a"), _product("b")
    client.force_login(редактор)

    response = client.post(
        f"/admin/catalog/product/{первый.pk}/change/",
        {
            "name": "Новое имя",
            "slug": первый.slug,
            "status": первый.status,
            "card_name": "",
            "short_description": "",
            "description": "",
            "brand": "",
            "meta_title": "",
            "meta_description": "",
            "article": "",
            "barcode": "",
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "attribute_values-TOTAL_FORMS": "0",
            "attribute_values-INITIAL_FORMS": "0",
            "price_records-TOTAL_FORMS": "0",
            "price_records-INITIAL_FORMS": "0",
            "compat_out-TOTAL_FORMS": "0",
            "compat_out-INITIAL_FORMS": "0",
            "compat_in-TOTAL_FORMS": "0",
            "compat_in-INITIAL_FORMS": "0",
            "_save_and_next": "1",
        },
    )

    первый.refresh_from_db()
    assert первый.name == "Новое имя"
    assert response.status_code == 302
    assert f"/admin/catalog/product/{второй.pk}/change/" in response["Location"]
