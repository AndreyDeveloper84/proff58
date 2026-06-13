import pytest

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
)


@pytest.fixture
def root_category(db):
    return Category.add_root(name="Инструменты", slug="instruments")


@pytest.fixture
def child_category(root_category):
    return root_category.add_child(name="Дрели", slug="drills")


@pytest.fixture
def product(child_category):
    return Product.objects.create(
        category=child_category,
        name="Дрель Bosch GSB 13",
        slug="bosch-gsb-13",
    )


@pytest.mark.django_db
def test_category_tree(root_category, child_category):
    assert child_category.get_parent().pk == root_category.pk
    assert root_category.get_children().count() == 1


@pytest.mark.django_db
def test_product_created_without_1c_link(product):
    assert product.code_1c == ""
    assert product.article == ""
    assert product.is_active is True


@pytest.mark.django_db
def test_product_slug_auto(child_category):
    p = Product.objects.create(category=child_category, name="Перфоратор Makita")
    # allow_unicode=True → кириллица остаётся в slug (валидный Unicode URL)
    assert "makita" in p.slug
    assert p.slug != ""


@pytest.mark.django_db
def test_eav_text_attribute(product):
    attr = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER, unit="Вт"
    )
    CategoryAttribute.objects.create(category=product.category, attribute=attr)
    val = ProductAttributeValue.objects.create(product=product, attribute=attr, value_integer=650)
    assert val.value == 650


@pytest.mark.django_db
def test_eav_select_attribute(product):
    attr = Attribute.objects.create(
        slug="chuck_type", name="Тип патрона", attribute_type=AttributeType.SELECT
    )
    option = AttributeOption.objects.create(attribute=attr, value="Быстрозажимной")
    val = ProductAttributeValue.objects.create(product=product, attribute=attr, value_option=option)
    assert val.value == option


@pytest.mark.django_db
def test_product_link_to_1c(product):
    product.code_1c = "000001234"
    product.article = "GSB13-RE"
    product.save()
    product.refresh_from_db()
    assert product.code_1c == "000001234"
    assert product.article == "GSB13-RE"
