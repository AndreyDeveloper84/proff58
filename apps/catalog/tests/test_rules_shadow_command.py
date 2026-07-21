import json
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogProcessingItem,
    CatalogProcessingRun,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)


def _category():
    return Category.add_root(name=f"Кат-{uuid.uuid4().hex[:8]}", slug=f"cat-{uuid.uuid4().hex[:8]}")


def _product(**kw):
    defaults = dict(
        category=_category(),
        name="",
        slug=f"p-{uuid.uuid4().hex[:8]}",
        original_name="",
        status=ProductStatus.IMPORTED,
        is_active=True,
        article="A1",
        content_locked=False,
        available_quantity=1,
        price="100",
    )
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _tool_type_attr():
    return Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )[0]


def _option(attr, value, slug):
    return AttributeOption.objects.get_or_create(
        attribute=attr, value=value, defaults={"slug": slug}
    )[0]


def _ruleset_file(tmp_path, slug="krep-shplinty"):
    data = {
        "version": 1,
        "ruleset_id": "tool_type.v1",
        "rules": [
            {
                "rule_ref": "tt-test-001",
                "option_slug": slug,
                "match": {"name_keywords_any": ["шплинт"]},
            }
        ],
        "negative_fixtures": [{"name": "Пассатижи комбинированные"}],
    }
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _db_counts():
    return (
        Product.objects.count(),
        ProductAttributeValue.objects.count(),
        CatalogChange.objects.count(),
        CatalogProcessingRun.objects.count(),
        CatalogProcessingItem.objects.count(),
    )


@pytest.mark.django_db
def test_shadow_command_report_and_zero_writes(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    target = _product(original_name="Шплинт 6,4х76 оцинкованный", article="A2")
    miss = _product(original_name="Пассатижи 180мм", article="A3")
    out = tmp_path / "report.json"
    ruleset = _ruleset_file(tmp_path)
    before = _db_counts()

    call_command(
        "catalog_rules_shadow",
        ruleset=str(ruleset),
        pool="in-stock",
        out=str(out),
        sample_size=10,
        seed=42,
    )

    assert _db_counts() == before  # ноль записей
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["counts"]["predictions"] == 1
    assert report["counts"]["collisions"] == 0
    assert report["pool"]["name"] == "in-stock"
    ids = [p["product_id"] for p in report["predictions"]]
    assert target.pk in ids and miss.pk not in ids
    assert report["predictions"][0]["rule_refs"] == ["tt-test-001"]
    assert report["sample"]["seed"] == 42
    assert len(report["ruleset_hash"]) == 64 and len(report["taxonomy_hash"]) == 64


@pytest.mark.django_db
def test_shadow_command_excludes_products_with_tool_type(tmp_path):
    attr = _tool_type_attr()
    opt = _option(attr, "Шплинты", "krep-shplinty")
    typed = _product(original_name="Шплинт 6,4х76", article="A4")
    ProductAttributeValue.objects.create(
        product=typed, attribute=attr, value_option=opt, source=Source.WEB, confidence=85
    )
    _product(original_name="Шплинт 3,2х50", article="A5")
    out = tmp_path / "report.json"
    call_command(
        "catalog_rules_shadow",
        ruleset=str(_ruleset_file(tmp_path)),
        pool="in-stock",
        out=str(out),
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    ids = [p["product_id"] for p in report["predictions"]]
    assert typed.pk not in ids  # перезапись запрещена: товар даже не оценивается
    assert report["counts"]["excluded_existing_tool_type"] == 1


@pytest.mark.django_db
def test_shadow_command_unknown_slug_fails(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    with pytest.raises(CommandError, match="отсутствуют в allowed"):
        call_command(
            "catalog_rules_shadow",
            ruleset=str(_ruleset_file(tmp_path, slug="net-takogo-tipa")),
            pool="in-stock",
            out=str(tmp_path / "r.json"),
        )


@pytest.mark.django_db
def test_shadow_command_sample_deterministic(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    for i in range(5):
        _product(original_name=f"Шплинт тип {i}", article=f"S{i}")
    out1, out2 = tmp_path / "r1.json", tmp_path / "r2.json"
    ruleset = _ruleset_file(tmp_path)
    for out in (out1, out2):
        call_command(
            "catalog_rules_shadow",
            ruleset=str(ruleset),
            pool="all",
            out=str(out),
            sample_size=3,
            seed=20260721,
        )
    s1 = json.loads(out1.read_text(encoding="utf-8"))["sample"]["product_ids"]
    s2 = json.loads(out2.read_text(encoding="utf-8"))["sample"]["product_ids"]
    assert s1 == s2 and len(s1) == 3
