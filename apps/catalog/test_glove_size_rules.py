"""ХАР-SIZE: размер перчаток — отдельный slug ``glove_size``, ``size`` остаётся numeric.

Дефект. Один slug ``size`` объявлен в словаре с двумя разными ``kind``:
``number``/«мм» у ``klyuchi-gaechnye``/``golovki`` («Размер под ключ») и ``select``
с буквенными опциями S…XXXL у ``siz-perchatki``. ``load_attributes`` создаёт ОДИН
``Attribute`` на slug, поэтому в БД он живёт как ``decimal`` (первый выигравший
блок), а объявление перчаток молча проигрывает — в плане это единственный
``conflicts``-элемент ``attribute_type kept=decimal declared=select``.

Последствие для витрины — «фильтр-призрак»: буквенное значение под ``decimal``
выбрасывается в ``_cast_facet_value`` (ValueError → значение пропускается, фасет
пустой и не эмитится), а ``range_filter_attributes`` тот же атрибут категории
всё равно объявляет диапазонным — ползунок без данных.

Решение владельца: **«size — отдельный slug»**, размер перчаток переезжает на
``glove_size`` (select), ``size`` остаётся числовым. Тесты ниже фиксируют дефект
(первые два падают до правки словаря) и проверяют, что новая схема призрака не
создаёт.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.facets import build_facets
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductStatus,
    StockStatus,
)
from apps.catalog.queries import range_filter_attributes

GLOVE_TOOL_TYPE = "siz-perchatki"
GLOVE_CATEGORY = "Перчатки и рукавицы"
GLOVE_SIZE_SLUG = "glove_size"
GLOVE_SIZE_OPTIONS = [
    ("S–M", "s-m"),
    ("L–XL", "l-xl"),
    ("XXXL", "xxxl"),
    ("XXL", "xxl"),
    ("XL", "xl"),
    ("XS", "xs"),
    ("S", "s"),
    ("M", "m"),
    ("L", "l"),
]


def _rules() -> dict:
    return json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))


def _declarations(slug: str) -> list[tuple[str, dict]]:
    """Все объявления атрибута в словаре: ``[(tool_type, блок), …]``."""
    return [
        (tt.get("tool_type", ""), a)
        for tt in _rules().get("tool_types", [])
        for a in tt.get("attributes", [])
        if a.get("slug") == slug
    ]


# --------------------------------------------------------------------------- #
# Дефект: один slug — два несовместимых типа
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_no_slug_declared_with_conflicting_kind():
    """Инвариант словаря: slug не может быть одновременно number и select."""
    kinds: dict[str, set[str]] = {}
    for tt in _rules().get("tool_types", []):
        for a in tt.get("attributes", []):
            kinds.setdefault(a["slug"], set()).add(a.get("kind", "text"))

    conflicting = {slug: sorted(k) for slug, k in kinds.items() if len(k) > 1}
    assert conflicting == {}, f"slug объявлены с разными kind: {conflicting}"


@pytest.mark.django_db
def test_real_rules_plan_has_no_attribute_type_conflicts():
    """План ``load_attributes`` на боевом словаре не содержит conflicts."""
    out = StringIO()
    call_command("load_attributes", "--dry-run", stdout=out)
    plan = json.loads(out.getvalue())

    conflicts = {r["slug"]: r["conflicts"] for r in plan["attributes"] if r["conflicts"]}
    assert conflicts == {}, f"конфликты типов в плане: {conflicts}"


# --------------------------------------------------------------------------- #
# Новая схема словаря
# --------------------------------------------------------------------------- #


def test_size_is_numeric_everywhere():
    """``size`` остаётся числовым «под ключ» и объявлен только у ключей/головок."""
    decls = _declarations("size")
    assert {tt for tt, _ in decls} == {"klyuchi-gaechnye", "golovki"}
    for _, a in decls:
        assert a["kind"] == "number"
        assert a["unit"] == "мм"


def test_glove_size_declared_as_select_with_all_options():
    """``glove_size`` — select у перчаток, все 9 опций перенесены без потерь."""
    decls = _declarations(GLOVE_SIZE_SLUG)
    assert [tt for tt, _ in decls] == [GLOVE_TOOL_TYPE]

    rule = decls[0][1]
    assert rule["kind"] == "select"
    assert rule["source"] == "keyword"
    assert rule["word_boundary"] is True
    assert rule["is_filter"] is True
    assert rule["is_seo_facet"] is True
    assert [(o["value"], o["slug"]) for o in rule["options"]] == GLOVE_SIZE_OPTIONS


def test_glove_size_option_keywords_unchanged():
    """Ключевые слова опций и их порядок (диапазоны раньше одиночных букв) целы."""
    rule = _declarations(GLOVE_SIZE_SLUG)[0][1]
    keywords = {o["slug"]: o["keywords"] for o in rule["options"]}
    assert keywords == {
        "s-m": ["s-m"],
        "l-xl": ["l-xl"],
        "xxxl": ["xxxl", "3xl"],
        "xxl": ["xxl"],
        "xl": ["xl"],
        "xs": ["xs"],
        "s": ["s"],
        "m": ["m"],
        "l": ["l"],
    }


@pytest.mark.django_db
def test_load_attributes_creates_select_glove_size_and_decimal_size():
    """Загрузка боевого словаря: два независимых атрибута, опции только у перчаток."""
    Category.add_root(name="Ручной инструмент", slug="ruchnoy", on_site=True)
    Category.add_root(name=GLOVE_CATEGORY, slug="perchatki", on_site=True)
    call_command("load_attributes")

    size = Attribute.objects.get(slug="size")
    glove = Attribute.objects.get(slug=GLOVE_SIZE_SLUG)
    assert (size.attribute_type, size.unit) == (AttributeType.DECIMAL, "мм")
    assert (glove.attribute_type, glove.unit) == (AttributeType.SELECT, "")
    assert AttributeOption.objects.filter(attribute=size).count() == 0
    assert AttributeOption.objects.filter(attribute=glove).count() == len(GLOVE_SIZE_OPTIONS)


@pytest.mark.django_db
def test_size_is_not_bound_to_glove_category():
    """Числовой ``size`` больше не садится на категорию перчаток."""
    Category.add_root(name="Ручной инструмент", slug="ruchnoy", on_site=True)
    gloves = Category.add_root(name=GLOVE_CATEGORY, slug="perchatki", on_site=True)
    call_command("load_attributes")

    bound = set(
        CategoryAttribute.objects.filter(category=gloves).values_list("attribute__slug", flat=True)
    )
    assert "size" not in bound
    assert GLOVE_SIZE_SLUG in bound


# --------------------------------------------------------------------------- #
# Витрина: фасет вместо фильтра-призрака
# --------------------------------------------------------------------------- #


def _glove_shelf() -> tuple[Category, Attribute]:
    gloves = Category.add_root(name=GLOVE_CATEGORY, slug="perchatki", on_site=True)
    attr = Attribute.objects.create(
        slug=GLOVE_SIZE_SLUG,
        name="Размер перчаток",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    for sort, (value, slug) in enumerate(GLOVE_SIZE_OPTIONS):
        AttributeOption.objects.create(attribute=attr, value=value, slug=slug, sort_order=sort)
    CategoryAttribute.objects.create(category=gloves, attribute=attr, is_filter=True)
    for i, value in enumerate(["XL", "XL", "M"]):
        Product.objects.create(
            category=gloves,
            name=f"Перчатки {i}",
            slug=f"perchatki-{i}",
            attrs_cache={GLOVE_SIZE_SLUG: value},
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_status=StockStatus.IN_STOCK,
        )
    return gloves, attr


@pytest.mark.django_db
def test_glove_size_is_a_checkbox_facet_not_a_range_filter():
    """SELECT-атрибут в range_filter_attributes не попадает, а в фасеты — попадает."""
    gloves, _ = _glove_shelf()

    assert range_filter_attributes(gloves) == []

    facet = next(f for f in build_facets(gloves)["facets"] if f["slug"] == GLOVE_SIZE_SLUG)
    assert facet["type"] == AttributeType.SELECT
    assert facet["is_nav"] is False
    assert {v["value"]: v["count"] for v in facet["values"]} == {"XL": 2, "M": 1}
    assert {v["slug"] for v in facet["values"]} == {"xl", "m"}


@pytest.mark.django_db
def test_old_scheme_produced_a_phantom_range_filter():
    """Контрольный замер прежней схемы: decimal ``size`` над буквенными значениями.

    Фасет пуст (``_cast_facet_value`` роняет «XL»), а range-фильтр атрибут всё
    равно объявляет — ползунок без данных. Ради этого и разводили slug.
    """
    gloves = Category.add_root(name=GLOVE_CATEGORY, slug="perchatki", on_site=True)
    size = Attribute.objects.create(
        slug="size",
        name="Размер «под ключ»",
        attribute_type=AttributeType.DECIMAL,
        unit="мм",
        is_filterable=True,
    )
    CategoryAttribute.objects.create(category=gloves, attribute=size, is_filter=True)
    Product.objects.create(
        category=gloves,
        name="Перчатки XL",
        slug="perchatki-xl",
        attrs_cache={"size": "XL"},
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=StockStatus.IN_STOCK,
    )

    assert [r["slug"] for r in range_filter_attributes(gloves)] == ["size"]
    assert [f for f in build_facets(gloves)["facets"] if f["slug"] == "size"] == []
