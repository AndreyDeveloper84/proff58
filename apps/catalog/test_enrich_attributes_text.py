"""``kind: text`` в write-path ``enrich_attributes`` (окно CODE-02).

Поверх ИНЛАЙН-словаря правил (tmp_path, НЕ ``data/attribute_rules.json`` — тот
правит параллельное окно CAT-14C) проверяем:

- значение пишется в ``ProductAttributeValue.value_text``, остальные value-поля
  обнулены; select-options для открытых кодов НЕ создаются;
- перезапись существующего значения — по приоритету источника (manual не
  затирается regex, regex перезаписывается regex);
- dry-run показывает text-значения в ``current_value``/``proposed_value``
  (эталонные ``attr_value_to_json``/``extracted_value_to_json``) и НИЧЕГО не
  пишет (снимок БД до/после равен).
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    ImportRun,
    Product,
    ProductAttributeValue,
    Source,
)

TT = "zap-shchetki-ugolnye"

RULES_DOC = {
    "source_priority": {"regex": 40, "keyword": 30, "inferred": 10, "manual": 100},
    "tool_types": [
        {
            "tool_type": TT,
            "attributes": [
                {
                    "slug": "analog_code",
                    "name": "Код аналога",
                    "kind": "text",
                    "source": "regex",
                    "regex": [r"\b(\d{1,3}-\d{1,4})\b", r"\b([a-z]{1,4}-?\d{1,5}[a-z0-9]?)\b"],
                }
            ],
        }
    ],
}


@pytest.fixture
def rules_path(tmp_path):
    (tmp_path / "attribute_rules.json").write_text(
        json.dumps(RULES_DOC, ensure_ascii=False), encoding="utf-8"
    )
    return str(tmp_path)


@pytest.fixture
def catalog(db, rules_path):
    """Топ-категория + атрибут tool_type с вариантом «Щётки угольные» + схема атрибутов."""
    top = Category.add_root(name="Запчасти", slug="zapchasti", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    option = AttributeOption.objects.create(attribute=tool_type, value="Щётки угольные", slug=TT)
    call_command("load_attributes", "--path", rules_path)
    return {"top": top, "tool_type": tool_type, "option": option}


def _make_product(catalog, name, code):
    product = Product.objects.create(category=catalog["top"], name=name, slug=code, code_1c=code)
    ProductAttributeValue.objects.create(
        product=product,
        attribute=catalog["tool_type"],
        value_option=catalog["option"],
        source=Source.MANUAL,
    )
    return product


def _enrich(rules_path, *args):
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--path", rules_path, *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def _pav_snapshot():
    return {
        (pav.product_id, pav.attribute.slug): (
            pav.value_text,
            pav.value_integer,
            str(pav.value_decimal) if pav.value_decimal is not None else None,
            pav.value_boolean,
            pav.value_option_id,
            pav.source,
            pav.confidence,
        )
        for pav in ProductAttributeValue.objects.all()
    }


def _cache_snapshot():
    return dict(Product.objects.values_list("id", "attrs_cache"))


def _analog_pav(product):
    return ProductAttributeValue.objects.get(product=product, attribute__slug="analog_code")


# --- боевой apply ------------------------------------------------------------


@pytest.mark.django_db
def test_text_value_written_to_value_text_only(catalog, rules_path):
    product = _make_product(catalog, "Щётка угольная CB-155", "s1")

    _enrich(rules_path)

    pav = _analog_pav(product)
    assert pav.value_text == "CB-155"
    assert pav.value_integer is None
    assert pav.value_decimal is None
    assert pav.value_boolean is None
    assert pav.value_option_id is None
    assert pav.source == Source.REGEX
    product.refresh_from_db()
    assert product.attrs_cache["analog_code"] == "CB-155"


@pytest.mark.django_db
def test_text_kind_creates_no_select_options(catalog, rules_path):
    _make_product(catalog, "Щётка угольная 13-102", "s2")

    _enrich(rules_path)

    # открытые коды — НЕ select: ни load_attributes, ни enrich не создают варианты
    assert not AttributeOption.objects.filter(attribute__slug="analog_code").exists()


@pytest.mark.django_db
def test_text_value_overwritten_by_equal_or_higher_priority(catalog, rules_path):
    product = _make_product(catalog, "Щётка угольная CB-155", "s3")
    attribute = Attribute.objects.get(slug="analog_code")
    ProductAttributeValue.objects.create(
        product=product, attribute=attribute, value_text="СТАРЫЙ", source=Source.REGEX
    )

    _enrich(rules_path)

    # regex (40) >= regex (40) — перезапись
    assert _analog_pav(product).value_text == "CB-155"


@pytest.mark.django_db
def test_text_value_not_overwritten_by_lower_priority(catalog, rules_path):
    product = _make_product(catalog, "Щётка угольная CB-155", "s4")
    attribute = Attribute.objects.get(slug="analog_code")
    ProductAttributeValue.objects.create(
        product=product, attribute=attribute, value_text="РУЧНОЕ", source=Source.MANUAL
    )

    _enrich(rules_path)

    # manual (100) > regex (40) — ручное значение не затирается
    assert _analog_pav(product).value_text == "РУЧНОЕ"


# --- dry-run ------------------------------------------------------------------


@pytest.mark.django_db
def test_dry_run_reports_text_values_and_writes_nothing(catalog, rules_path):
    product = _make_product(catalog, "Щётка угольная CB-155", "s5")
    attribute = Attribute.objects.get(slug="analog_code")
    # второй товар — с существующим значением: dry-run обязан показать update
    # с current_value (эталонный attr_value_to_json) и proposed_value
    other = _make_product(catalog, "Щётка угольная 13-102", "s6")
    ProductAttributeValue.objects.create(
        product=other, attribute=attribute, value_text="СТАРЫЙ", source=Source.REGEX
    )

    before_pav = _pav_snapshot()
    before_cache = _cache_snapshot()
    before_runs = list(ImportRun.objects.values_list("id", flat=True))

    out, _ = _enrich(rules_path, "--dry-run")
    report = json.loads(out)

    assert _pav_snapshot() == before_pav
    assert _cache_snapshot() == before_cache
    assert list(ImportRun.objects.values_list("id", flat=True)) == before_runs

    rows = {r["product_id"]: r for r in report["rows"] if r["attribute"] == "analog_code"}
    create_row = rows[product.id]
    assert create_row["action"] == "create"
    assert create_row["current_value"] is None
    assert create_row["proposed_value"] == "CB-155"
    update_row = rows[other.id]
    assert update_row["action"] == "update"
    assert update_row["current_value"] == "СТАРЫЙ"
    assert update_row["proposed_value"] == "13-102"
