"""Чек-лист готовности товара.

Смысл — человеку без опыта видно не «ошибку валидации», а что именно осталось
сделать. Тесты закрепляют состав пунктов и то, что блокирующие публикацию
отделены от косметических.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductImage,
)
from apps.catalog.readiness import blocking_checks, product_checks, readiness_percent


@pytest.fixture
def категория(db):
    return Category.add_root(name="Перфораторы", slug="perforatory")


@pytest.fixture
def товар(db, категория):
    return Product.objects.create(
        name="Перфоратор Makita HR2470",
        slug="makita-hr2470",
        code_1c="r-1",
        category=категория,
        price=Decimal("8990.00"),
        short_description="Надёжный перфоратор",
    )


def _labels(checks):
    return [c.label for c in checks]


def test_полностью_готовый_товар_даёт_сто_процентов(товар):
    ProductImage.objects.create(product=товар, image="products/a.jpg", is_main=True)

    checks = product_checks(товар)

    assert readiness_percent(checks) == 100
    assert blocking_checks(checks) == []


def test_без_категории_публикация_заблокирована(db):
    товар = Product.objects.create(
        name="Ничей товар", slug="nichey", code_1c="r-2", price=Decimal("100.00")
    )

    blocking = blocking_checks(product_checks(товар))

    assert [c.label for c in blocking] == ["Категория выбрана"]


def test_нехватка_обязательной_характеристики_видна_с_именем(товар, категория):
    мощность = Attribute.objects.create(
        name="Мощность", slug="moshchnost", attribute_type=AttributeType.INTEGER, unit="Вт"
    )
    CategoryAttribute.objects.create(category=категория, attribute=мощность, is_required=True)

    checks = product_checks(товар)

    assert any("не хватает Мощность" in label for label in _labels(checks))
    assert any(c.blocks_publication and not c.ok for c in checks)


def test_заполненная_характеристика_снимает_пункт(товар, категория):
    мощность = Attribute.objects.create(
        name="Мощность", slug="moshchnost", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=категория, attribute=мощность, is_required=True)
    ProductAttributeValue.objects.create(product=товар, attribute=мощность, value_integer=780)

    checks = product_checks(товар)

    assert "Обязательные характеристики заполнены" in _labels(checks)
    assert blocking_checks(checks) == []


def test_фото_и_описание_не_блокируют_публикацию(товар):
    """Пустая карточка — плохо, но это не причина не пускать товар на сайт."""
    товар.short_description = ""
    товар.description = ""

    checks = product_checks(товар)
    невыполненные = {c.label for c in checks if not c.ok}

    assert "Есть фотография" in невыполненные
    assert "Есть описание" in невыполненные
    assert blocking_checks(checks) == []


def test_пункт_про_главное_фото_появляется_только_когда_фото_есть(товар):
    assert "Выбрано главное фото" not in _labels(product_checks(товар))

    ProductImage.objects.create(product=товар, image="products/b.jpg", is_main=False)

    checks = product_checks(товар)
    assert "Выбрано главное фото" in _labels(checks)
    assert not next(c for c in checks if c.label == "Выбрано главное фото").ok


def test_процент_считается_по_доле_выполненных(товар):
    checks = product_checks(товар)
    выполнено = sum(1 for c in checks if c.ok)

    assert readiness_percent(checks) == round(100 * выполнено / len(checks))


def test_пустой_чеклист_не_делит_на_ноль():
    assert readiness_percent([]) == 0
