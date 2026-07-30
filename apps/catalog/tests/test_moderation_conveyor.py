"""Конвейер модерации: заполнить — опубликовать — следующий.

Смысл экрана — убрать навигацию из разбора каталога. Поэтому проверяем не
только «поля сохранились», но и что очередь двигается и что публикация не
проходит мимо правил.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.catalog import moderation
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)

User = get_user_model()
URL = "/admin/catalog/product/moderate/"


@pytest.fixture
def модератор(db):
    return User.objects.create_superuser(phone="+79997770000", password="pwd12345")


@pytest.fixture
def категория(db):
    cat = Category.add_root(name="Перфораторы", slug="perf-mod")
    мощность = Attribute.objects.create(
        name="Мощность", slug="m-mod", attribute_type=AttributeType.INTEGER, unit="Вт"
    )
    патрон = Attribute.objects.create(
        name="Патрон", slug="p-mod", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=патрон, value="SDS-plus", slug="sds-plus")
    CategoryAttribute.objects.create(category=cat, attribute=мощность, is_required=True)
    CategoryAttribute.objects.create(category=cat, attribute=патрон, is_required=False)
    return {"cat": cat, "мощность": мощность, "патрон": патрон}


def _product(name, **kwargs):
    defaults = {
        "slug": name,
        "code_1c": f"m-{name}",
        "status": ProductStatus.IMPORTED,
        "price": Decimal("5000.00"),
    }
    defaults.update(kwargs)
    return Product.objects.create(name=name, **defaults)


def test_очередь_совпадает_с_счётчиком_дашборда(db, категория):
    _product("a")
    _product("b", category=категория["cat"], status=ProductStatus.PUBLISHED)

    assert [p.name for p in moderation.queue()] == ["a"]


def test_следующий_идёт_за_текущим(db):
    первый, второй = _product("a"), _product("b")

    assert moderation.next_product(after_id=первый.pk).pk == второй.pk


def test_после_последнего_возвращаемся_к_началу(db):
    первый = _product("a")

    assert moderation.next_product(after_id=первый.pk).pk == первый.pk


def test_форма_строит_поля_характеристик_категории(db, категория):
    товар = _product("a", category=категория["cat"])

    form = moderation.ModerationForm(product=товар)
    имена = [f.name for f in form.attribute_fields]

    assert имена == [
        f"attr_{категория['мощность'].pk}",  # обязательная — первой
        f"attr_{категория['патрон'].pk}",
    ]


def test_без_категории_характеристик_нет(db):
    form = moderation.ModerationForm(product=_product("a"))

    assert form.attribute_fields == []


def test_сохранение_проставляет_категорию_и_характеристику(db, категория):
    товар = _product("a")

    form = moderation.ModerationForm(
        data={
            "category": категория["cat"].pk,
            "card_name": "Короткое",
            "short_description": "Текст",
            f"attr_{категория['мощность'].pk}": "800",
        },
        product=товар,
    )
    assert form.is_valid(), form.errors
    form.apply()

    товар.refresh_from_db()
    assert товар.category_id == категория["cat"].pk
    assert товар.category_is_manual is True  # авторазбор 1С это больше не тронет
    assert товар.card_name == "Короткое"


def test_значение_характеристики_считается_подтверждённым_человеком(db, категория):
    товар = _product("a", category=категория["cat"])

    form = moderation.ModerationForm(
        data={"category": категория["cat"].pk, f"attr_{категория['мощность'].pk}": "800"},
        product=товар,
    )
    assert form.is_valid(), form.errors
    form.apply()

    pav = ProductAttributeValue.objects.get(product=товар, attribute=категория["мощность"])
    assert pav.value_integer == 800
    assert pav.source == Source.MANUAL and pav.confidence == 100


def test_очистка_поля_удаляет_значение(db, категория):
    товар = _product("a", category=категория["cat"])
    ProductAttributeValue.objects.create(
        product=товар, attribute=категория["мощность"], value_integer=700
    )

    form = moderation.ModerationForm(
        data={"category": категория["cat"].pk, f"attr_{категория['мощность'].pk}": ""},
        product=товар,
    )
    assert form.is_valid(), form.errors
    form.apply()

    assert not ProductAttributeValue.objects.filter(product=товар).exists()


def test_публикация_без_обязательной_характеристики_не_проходит(db, категория):
    товар = _product("a", category=категория["cat"])

    errors = moderation.publish(товар)

    товар.refresh_from_db()
    assert errors and товар.status != ProductStatus.PUBLISHED


def test_публикация_проходит_когда_всё_заполнено(db, категория):
    товар = _product("a", category=категория["cat"])
    ProductAttributeValue.objects.create(
        product=товар, attribute=категория["мощность"], value_integer=800
    )

    assert moderation.publish(товар) == []
    товар.refresh_from_db()
    assert товар.status == ProductStatus.PUBLISHED and товар.is_active


# --------------------------------------------------------------------- экран


def test_экран_открывается_и_показывает_первый_товар(client, модератор, db):
    _product("первый")
    client.force_login(модератор)

    body = client.get(URL).content.decode()

    assert "первый" in body and "осталось разобрать" in body


def test_на_пустой_очереди_экран_говорит_что_всё_разобрано(client, модератор, db):
    client.force_login(модератор)

    assert "Очередь пуста" in client.get(URL).content.decode()


def test_пропустить_ведёт_к_следующему_не_меняя_товар(client, модератор, db):
    первый, второй = _product("a"), _product("b")
    client.force_login(модератор)

    response = client.post(URL, {"product_id": первый.pk, "action": "skip"})

    первый.refresh_from_db()
    assert response.status_code == 302
    assert str(второй.pk) in response["Location"]
    assert первый.status == ProductStatus.IMPORTED


def test_публикация_с_экрана_заполняет_и_публикует(client, модератор, категория):
    товар = _product("a")
    client.force_login(модератор)

    client.post(
        URL,
        {
            "product_id": товар.pk,
            "action": "publish",
            "category": категория["cat"].pk,
            f"attr_{категория['мощность'].pk}": "900",
        },
    )

    товар.refresh_from_db()
    assert товар.status == ProductStatus.PUBLISHED
    assert товар.attribute_values.get().value_integer == 900


def test_публикация_без_характеристики_возвращает_на_экран_с_причиной(client, модератор, категория):
    товар = _product("a")
    client.force_login(модератор)

    body = client.post(
        URL, {"product_id": товар.pk, "action": "publish", "category": категория["cat"].pk}
    ).content.decode()

    товар.refresh_from_db()
    assert товар.status != ProductStatus.PUBLISHED
    assert "Опубликовать пока нельзя" in body


def test_без_прав_не_пускает(client, db):
    _product("a")
    user = User.objects.create_user(phone="+79996660000", password="pwd12345", is_staff=True)
    client.force_login(user)

    assert client.get(URL).status_code in (302, 403)


def test_ссылка_на_конвейер_именованная():
    assert reverse("admin:catalog_product_moderate") == URL
