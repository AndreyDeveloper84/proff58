"""Тесты операторской очереди модерации каталога (#51).

Покрывают:
  * переходы IMPORTED → NEEDS_REVIEW → PUBLISHED (guard публикации);
  * колонку moderation_reason (причина для невалидного, «—» для валидного);
  * ModerationQueueFilter (attention / needs_review / imported);
  * команду publish_catalog (--all не публикует невалидные, счётчик «пропущено»);
  * отсутствие N+1 в колонке на отфильтрованной выборке.

Стиль — как в test_admin_smoke.py: проверяем эффект в БД и значения методов,
а не парсим HTML.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.admin import ModerationQueueFilter, ProductAdmin
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
)


def _admin():
    return ProductAdmin(Product, AdminSite())


# ---------------------------------------------------------------------------
# Переход IMPORTED → NEEDS_REVIEW → PUBLISHED
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lifecycle_imported_to_published():
    cat = Category.add_root(name="Дрели", slug="lc-drills")
    attr = Attribute.objects.create(
        slug="lc-power", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)

    # IMPORTED без категории — публиковать нельзя.
    p = Product.objects.create(name="Дрель", slug="lc-drill", status=ProductStatus.IMPORTED)
    assert p.publication_errors() == ["Укажите категорию"]

    # Назначили категорию → нужна обязательная характеристика.
    p.category = cat
    p.status = ProductStatus.NEEDS_REVIEW
    p.save()
    assert p.missing_required_attributes() == ["Мощность"]
    assert p.publication_errors() != []

    # Заполнили обязательную характеристику → можно публиковать.
    ProductAttributeValue.objects.create(product=p, attribute=attr, value_integer=600)
    assert p.missing_required_attributes() == []
    assert p.publication_errors() == []

    p.status = ProductStatus.PUBLISHED
    p.full_clean()  # guard не срабатывает


# ---------------------------------------------------------------------------
# Колонка moderation_reason
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_moderation_reason_no_category():
    p = Product.objects.create(name="Без кат", slug="mr-nocat", status=ProductStatus.IMPORTED)
    assert _admin().moderation_reason(p) == "Нет категории"


@pytest.mark.django_db
def test_moderation_reason_missing_required():
    cat = Category.add_root(name="Пилы", slug="mr-saws")
    a1 = Attribute.objects.create(
        slug="mr-volt", name="Напряжение", attribute_type=AttributeType.INTEGER
    )
    a2 = Attribute.objects.create(
        slug="mr-torque", name="Момент", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=a1, is_required=True)
    CategoryAttribute.objects.create(category=cat, attribute=a2, is_required=True)
    p = Product.objects.create(
        name="Пила", slug="mr-saw", category=cat, status=ProductStatus.NEEDS_REVIEW
    )
    reason = _admin().moderation_reason(p)
    assert reason.startswith("Не хватает:")
    assert "Напряжение" in reason and "Момент" in reason


@pytest.mark.django_db
def test_moderation_reason_published_is_dash():
    cat = Category.add_root(name="ОК", slug="mr-ok")
    p = Product.objects.create(
        name="Опубл", slug="mr-pub", category=cat, status=ProductStatus.PUBLISHED, is_active=True
    )
    assert _admin().moderation_reason(p) == "—"


@pytest.mark.django_db
def test_moderation_reason_valid_nonpublished_is_dash():
    # Не опубликован, но без ошибок (категория есть, обязательных нет) → «—».
    cat = Category.add_root(name="Готов", slug="mr-ready")
    p = Product.objects.create(
        name="Готов", slug="mr-ready-prod", category=cat, status=ProductStatus.DRAFT
    )
    assert _admin().moderation_reason(p) == "—"


# ---------------------------------------------------------------------------
# ModerationQueueFilter
# ---------------------------------------------------------------------------


def _filter_qs(value):
    # Django 5: SimpleListFilter ждёт значения параметров списком (как QueryDict).
    flt = ModerationQueueFilter(
        request=None, params={"moderation": [value]}, model=Product, model_admin=_admin()
    )
    return set(flt.queryset(None, Product.objects.all()).values_list("slug", flat=True))


@pytest.mark.django_db
def test_moderation_filter_subsets():
    cat = Category.add_root(name="F", slug="fq-cat")

    imported = Product.objects.create(
        name="i", slug="fq-imported", category=cat, status=ProductStatus.IMPORTED
    )
    needs = Product.objects.create(
        name="n", slug="fq-needs", category=cat, status=ProductStatus.NEEDS_REVIEW
    )
    draft_nocat = Product.objects.create(
        name="d", slug="fq-draft-nocat", status=ProductStatus.DRAFT
    )
    draft_ok = Product.objects.create(
        name="dok", slug="fq-draft-ok", category=cat, status=ProductStatus.DRAFT
    )
    published = Product.objects.create(
        name="p", slug="fq-pub", category=cat, status=ProductStatus.PUBLISHED, is_active=True
    )

    assert _filter_qs("imported") == {imported.slug}
    assert _filter_qs("needs_review") == {needs.slug}

    # attention: не published И (без категории ИЛИ status in imported/needs_review).
    attention = _filter_qs("attention")
    assert imported.slug in attention
    assert needs.slug in attention
    assert draft_nocat.slug in attention  # без категории
    assert draft_ok.slug not in attention  # draft с категорией, без обязательных
    assert published.slug not in attention


# ---------------------------------------------------------------------------
# publish_catalog: единое правило публикации
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publish_catalog_skips_invalid():
    cat = Category.add_root(name="Pub", slug="pc-cat")
    attr = Attribute.objects.create(
        slug="pc-power", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)

    valid = Product.objects.create(
        name="Валидный", slug="pc-valid", category=cat, status=ProductStatus.IMPORTED
    )
    ProductAttributeValue.objects.create(product=valid, attribute=attr, value_integer=500)
    # Невалидный: нет обязательной характеристики.
    no_attr = Product.objects.create(
        name="Без хар", slug="pc-noattr", category=cat, status=ProductStatus.IMPORTED
    )
    # Невалидный: нет категории.
    no_cat = Product.objects.create(name="Без кат", slug="pc-nocat", status=ProductStatus.IMPORTED)

    out = StringIO()
    call_command("publish_catalog", "--all", stdout=out)
    output = out.getvalue()

    valid.refresh_from_db()
    no_attr.refresh_from_db()
    no_cat.refresh_from_db()

    assert valid.status == ProductStatus.PUBLISHED and valid.is_active is True
    assert no_attr.status != ProductStatus.PUBLISHED
    assert no_cat.status != ProductStatus.PUBLISHED

    assert "Опубликовано: 1" in output
    assert "Пропущено: 2" in output


@pytest.mark.django_db
def test_publish_catalog_dry_run_counts():
    cat = Category.add_root(name="Dry", slug="pc-dry-cat")
    attr = Attribute.objects.create(
        slug="pc-dry-power", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)
    valid = Product.objects.create(
        name="V", slug="pc-dry-valid", category=cat, status=ProductStatus.IMPORTED
    )
    ProductAttributeValue.objects.create(product=valid, attribute=attr, value_integer=300)
    Product.objects.create(
        name="X", slug="pc-dry-invalid", category=cat, status=ProductStatus.IMPORTED
    )

    out = StringIO()
    call_command("publish_catalog", "--all", "--dry-run", stdout=out)
    output = out.getvalue()

    valid.refresh_from_db()
    assert valid.status == ProductStatus.IMPORTED  # dry-run ничего не меняет
    assert "К публикации: 1" in output
    assert "Пропущено: 1" in output


# ---------------------------------------------------------------------------
# Отсутствие N+1 в колонке moderation_reason на отфильтрованной выборке
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_moderation_reason_no_n_plus_one():
    cat = Category.add_root(name="N1", slug="n1-cat")
    attr = Attribute.objects.create(
        slug="n1-power", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=cat, attribute=attr, is_required=True)

    for i in range(10):
        Product.objects.create(
            name=f"Товар {i}",
            slug=f"n1-prod-{i}",
            category=cat,
            status=ProductStatus.NEEDS_REVIEW,
        )

    admin_obj = _admin()
    # Эмулируем рендер changelist: get_queryset с prefetch + один проход по строкам.
    request = type("R", (), {"GET": {}})()
    qs = admin_obj.get_queryset(request)

    with CaptureQueriesContext(connection) as ctx:
        products = list(qs)  # select_related + prefetch (несколько запросов на загрузку)
        for p in products:
            admin_obj.moderation_reason(p)

    # Мягкая граница: запросов на загрузку (товары + prefetch attribute_values) +
    # один запрос на required-атрибуты единственной категории. Без N+1 по товарам
    # это заведомо < 10. Берём запас.
    assert len(ctx.captured_queries) <= 6, [q["sql"] for q in ctx.captured_queries]
