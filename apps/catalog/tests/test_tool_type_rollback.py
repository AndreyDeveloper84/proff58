"""Тесты контура отката применённого ``tool_type`` (Wave 7.1 / Stage H5).

Проверяются три свойства из ТЗ H5: откат идемпотентен; частичный сбой не
оставляет полуприменённого состояния; откат поверх изменившегося baseline даёт
conflict, а не молчаливую перезапись.
"""

import json

import pytest

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Product,
    ProductAttributeValue,
)
from apps.catalog.tool_type_rollback import (
    SNAPSHOT_SCHEMA_VERSION,
    RollbackError,
    apply_rollback,
    build_snapshot,
    load_snapshot,
    plan_rollback,
    snapshot_bytes,
    verify_post_state,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def taxonomy():
    """Атрибут tool_type с тремя вариантами."""
    attribute = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    options = {
        slug: AttributeOption.objects.create(attribute=attribute, slug=slug, value=value)
        for slug, value in (("bury", "Буры"), ("sverla", "Свёрла"), ("koronki", "Коронки"))
    }
    return attribute, options


def _product(slug, *, option=None, attribute=None, cache_value=None):
    product = Product.objects.create(slug=slug, original_name=slug, name=slug)
    if option is not None:
        ProductAttributeValue.objects.create(
            product=product, attribute=attribute, value_option=option
        )
    product.attrs_cache = {"tool_type": cache_value} if cache_value else {}
    product.save(update_fields=["attrs_cache"])
    return product


# --- снимок ---


def test_snapshot_records_explicit_rows_for_selected_products(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    p2 = _product("p2")

    doc = build_snapshot(product_ids=[p2.id, p1.id])

    canonical = doc["canonical"]
    assert canonical["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert canonical["attribute_slug"] == "tool_type"
    assert canonical["rows_count"] == 2
    assert canonical["rows"] == [
        {
            "product_id": p1.id,
            "option_slug": "bury",
            "option_value": "Буры",
            "attrs_cache_tool_type": "Буры",
        },
        {
            "product_id": p2.id,
            "option_slug": None,
            "option_value": None,
            "attrs_cache_tool_type": None,
        },
    ]


def test_snapshot_is_byte_stable_across_runs(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")

    first = snapshot_bytes(build_snapshot(product_ids=[p1.id]))
    second = snapshot_bytes(build_snapshot(product_ids=[p1.id]))

    assert first == second


def test_snapshot_by_option_slug_selects_products_carrying_that_option(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    _product("p2", option=options["sverla"], attribute=attribute, cache_value="Свёрла")

    doc = build_snapshot(option_slugs=["bury"])

    assert [row["product_id"] for row in doc["canonical"]["rows"]] == [p1.id]
    assert doc["canonical"]["selector"] == {"kind": "option_slugs", "value": ["bury"]}


def test_snapshot_requires_exactly_one_selector(taxonomy):
    with pytest.raises(RollbackError, match="ровно один селектор"):
        build_snapshot()


def test_snapshot_fails_closed_on_unknown_product_id(taxonomy):
    with pytest.raises(RollbackError, match="не найдены"):
        build_snapshot(product_ids=[999999])


def test_load_snapshot_rejects_tampered_canonical_hash(taxonomy, tmp_path):
    p1 = _product("p1")
    doc = build_snapshot(product_ids=[p1.id])
    doc["canonical"]["rows"][0]["option_slug"] = "bury"
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RollbackError, match="canonical_hash"):
        load_snapshot(path)


# --- план отката: noop / write / conflict ---


def test_plan_marks_write_when_live_matches_from(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after = build_snapshot(product_ids=[p1.id])

    plan = plan_rollback(after, before)

    assert plan.counts == {"noop": 0, "write": 1, "conflict": 0}
    assert plan.feasible is True


def test_plan_marks_noop_when_live_already_at_target(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).delete()

    plan = plan_rollback(after, before)

    assert plan.counts == {"noop": 1, "write": 0, "conflict": 0}
    assert plan.feasible is True


def test_plan_reports_conflict_when_live_drifted_from_both_snapshots(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])

    plan = plan_rollback(after, before)

    assert plan.counts == {"noop": 0, "write": 0, "conflict": 1}
    assert plan.feasible is False
    assert plan.conflicts[0]["product_id"] == p1.id
    assert plan.conflicts[0]["live_option_slug"] == "koronki"


def test_plan_reports_conflict_when_product_disappeared(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    p2 = _product("p2")
    after = build_snapshot(product_ids=[p1.id, p2.id])
    before = build_snapshot(product_ids=[p1.id, p2.id])
    Product.objects.filter(id=p1.id).delete()

    plan = plan_rollback(after, before)

    assert plan.counts["conflict"] == 1
    assert plan.conflicts[0]["reason"] == "product_missing"


# --- fail-closed валидации пары снимков ---


def test_plan_rejects_snapshots_covering_different_products(taxonomy):
    p1 = _product("p1")
    p2 = _product("p2")
    after = build_snapshot(product_ids=[p1.id])
    before = build_snapshot(product_ids=[p2.id])

    with pytest.raises(RollbackError, match="разные множества товаров"):
        plan_rollback(after, before)


def test_plan_rejects_target_option_absent_in_live_taxonomy(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["sverla"])
    after = build_snapshot(product_ids=[p1.id])
    AttributeOption.objects.filter(slug="bury").delete()

    with pytest.raises(RollbackError, match="нет в live"):
        plan_rollback(after, before)


def test_plan_rejects_taxonomy_drift_between_snapshot_and_live(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after = build_snapshot(product_ids=[p1.id])
    AttributeOption.objects.create(attribute=attribute, slug="novaya", value="Новая")

    with pytest.raises(RollbackError, match="taxonomy_identity"):
        plan_rollback(after, before)


# --- применение отката ---


def test_apply_restores_previous_option_and_cache(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Коронки"})
    after = build_snapshot(product_ids=[p1.id])

    stats = apply_rollback(plan_rollback(after, before))

    assert stats["written"] == 1
    pav = ProductAttributeValue.objects.get(product=p1, attribute=attribute)
    assert pav.value_option.slug == "bury"
    assert Product.objects.get(id=p1.id).attrs_cache["tool_type"] == "Буры"


def test_apply_deletes_pav_when_previous_state_had_none(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Буры", "brand": "X"})
    after = build_snapshot(product_ids=[p1.id])

    apply_rollback(plan_rollback(after, before))

    assert not ProductAttributeValue.objects.filter(product=p1, attribute=attribute).exists()
    cache = Product.objects.get(id=p1.id).attrs_cache
    assert "tool_type" not in cache
    assert cache["brand"] == "X"


def test_apply_is_idempotent_second_run_writes_nothing(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Коронки"})
    after = build_snapshot(product_ids=[p1.id])

    apply_rollback(plan_rollback(after, before))
    second = apply_rollback(plan_rollback(after, before))

    assert second == {"written": 0, "noop": 1}
    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "bury"


def test_apply_refuses_plan_with_conflicts(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])

    with pytest.raises(RollbackError, match="conflict"):
        apply_rollback(plan_rollback(after, before))

    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "koronki"


def test_partial_failure_leaves_no_half_applied_state(taxonomy, monkeypatch):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    p2 = _product("p2", option=options["sverla"], attribute=attribute, cache_value="Свёрла")
    before = build_snapshot(product_ids=[p1.id, p2.id])
    ProductAttributeValue.objects.filter(product__in=[p1, p2]).update(
        value_option=options["koronki"]
    )
    Product.objects.filter(id__in=[p1.id, p2.id]).update(attrs_cache={"tool_type": "Коронки"})
    after = build_snapshot(product_ids=[p1.id, p2.id])

    import apps.catalog.tool_type_rollback as module

    original = module.flush_attrs_cache_merged

    def boom(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("сбой на середине")

    monkeypatch.setattr(module, "flush_attrs_cache_merged", boom)

    with pytest.raises(RuntimeError, match="сбой на середине"):
        apply_rollback(plan_rollback(after, before))

    live = {
        pav.product_id: pav.value_option.slug
        for pav in ProductAttributeValue.objects.select_related("value_option")
    }
    assert live == {p1.id: "koronki", p2.id: "koronki"}
    assert Product.objects.get(id=p1.id).attrs_cache == {"tool_type": "Коронки"}


# --- post-audit ---


def test_post_audit_passes_when_live_equals_target_snapshot(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Коронки"})
    after = build_snapshot(product_ids=[p1.id])

    apply_rollback(plan_rollback(after, before))
    audit = verify_post_state(before)

    assert audit["passed"] is True
    assert audit["diffs"] == []


def test_post_audit_fails_and_reports_diff_when_live_drifted(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Коронки"})

    audit = verify_post_state(before)

    assert audit["passed"] is False
    assert audit["diffs"]
