import pytest

from apps.catalog.categorization import ProductHint, categorize
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    CategoryMappingRule,
    MappingRuleType,
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
    assert product.code_1c is None
    assert product.article == ""
    # по умолчанию товар не виден на витрине (статус imported, is_active=False)
    assert product.is_active is False
    assert product.is_visible is False


@pytest.mark.django_db
def test_product_slug_auto(child_category):
    p = Product.objects.create(category=child_category, name="Перфоратор Makita")
    # allow_unicode=True → кириллица остаётся в slug (валидный Unicode URL)
    assert "makita" in p.slug
    assert p.slug != ""


@pytest.mark.django_db
def test_product_duplicate_names_get_unique_slugs():
    # одинаковые имена → slug дедуплицируется числовым суффиксом, без IntegrityError
    p1 = Product.objects.create(name="Перфоратор")
    p2 = Product.objects.create(name="Перфоратор")
    p3 = Product.objects.create(name="Перфоратор")
    assert p1.slug == "перфоратор"
    assert p2.slug == "перфоратор-2"
    assert p3.slug == "перфоратор-3"
    assert Product.objects.filter(slug__startswith="перфоратор").count() == 3


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


# --- Авторазбор категорий (categorization) ---


@pytest.mark.django_db
def test_categorize_by_name_contains(child_category):
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS,
        pattern="перфоратор",
        target_category=child_category,
    )
    cat, rule = categorize(ProductHint(name="Перфоратор Bosch GBH 2-26"))
    assert cat == child_category
    assert rule is not None


@pytest.mark.django_db
def test_categorize_by_article(child_category):
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.ARTICLE, pattern="BOSCH-123", target_category=child_category
    )
    cat, _ = categorize(ProductHint(article="bosch-123"))  # регистр игнорируется
    assert cat == child_category


@pytest.mark.django_db
def test_categorize_by_brand_prefix(child_category):
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.BRAND_PREFIX,
        pattern="GWS",
        brand="Bosch",
        target_category=child_category,
    )
    cat, _ = categorize(ProductHint(name="Bosch GWS 850", brand="Bosch"))
    assert cat == child_category
    # другой бренд — не срабатывает
    cat2, _ = categorize(ProductHint(name="Makita GWS-копия", brand="Makita"))
    assert cat2 is None


@pytest.mark.django_db
def test_categorize_priority(root_category, child_category):
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS,
        pattern="дрель",
        target_category=root_category,
        priority=200,
    )
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS,
        pattern="дрель",
        target_category=child_category,
        priority=10,
    )
    cat, _ = categorize(ProductHint(name="Ударная дрель"))
    assert cat == child_category  # меньший priority выигрывает


@pytest.mark.django_db
def test_categorize_no_match():
    cat, rule = categorize(ProductHint(name="Нечто непонятное"))
    assert cat is None
    assert rule is None
