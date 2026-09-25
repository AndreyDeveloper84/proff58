"""Тесты CLI-контура отката и понижения версии словаря (Wave 7.1 / Stage H5).

Проверяются exit codes (0/1/2/3), read-only по умолчанию и то, что применение
требует явного ``--apply``.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Product,
    ProductAttributeValue,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def taxonomy():
    attribute = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    options = {
        slug: AttributeOption.objects.create(attribute=attribute, slug=slug, value=value)
        for slug, value in (("bury", "Буры"), ("koronki", "Коронки"))
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


def _snapshot(tmp_path, name, **kwargs):
    out = tmp_path / name
    buf = StringIO()
    call_command("catalog_tool_type_snapshot", out=str(out), stdout=buf, **kwargs)
    return out, buf.getvalue()


def _rollback(from_path, to_path, **kwargs):
    buf = StringIO()
    call_command(
        "catalog_tool_type_rollback",
        **{"from": str(from_path), "to": str(to_path)},
        stdout=buf,
        **kwargs,
    )
    return buf.getvalue()


# --- команда снимка ---


def test_snapshot_command_writes_byte_stable_artifact(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")

    first, out = _snapshot(tmp_path, "a.json", product_ids=str(p1.id))
    second, _ = _snapshot(tmp_path, "b.json", product_ids=str(p1.id))

    assert first.read_bytes() == second.read_bytes()
    assert "rows=1" in out
    assert json.loads(first.read_text(encoding="utf-8"))["canonical"]["rows_count"] == 1


def test_snapshot_command_writes_nothing_to_database(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = (ProductAttributeValue.objects.count(), AttributeOption.objects.count())

    _snapshot(tmp_path, "a.json", product_ids=str(p1.id))

    assert (ProductAttributeValue.objects.count(), AttributeOption.objects.count()) == before


def test_snapshot_command_selects_by_option_slug(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    _product("p2", option=options["koronki"], attribute=attribute, cache_value="Коронки")

    path, _ = _snapshot(tmp_path, "a.json", option_slug=["bury"])

    rows = json.loads(path.read_text(encoding="utf-8"))["canonical"]["rows"]
    assert [r["product_id"] for r in rows] == [p1.id]


def test_snapshot_command_selects_all_products_with_tool_type(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    p2 = _product("p2", option=options["koronki"], attribute=attribute, cache_value="Коронки")
    _product("p3")

    path, _ = _snapshot(tmp_path, "a.json", all_with_tool_type=True)

    rows = json.loads(path.read_text(encoding="utf-8"))["canonical"]["rows"]
    assert sorted(r["product_id"] for r in rows) == sorted([p1.id, p2.id])


def test_snapshot_command_refuses_to_overwrite_without_force(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    path, _ = _snapshot(tmp_path, "a.json", product_ids=str(p1.id))
    ProductAttributeValue.objects.filter(product=p1).delete()

    with pytest.raises(CommandError) as exc_info:
        _snapshot(tmp_path, "a.json", product_ids=str(p1.id))

    assert exc_info.value.returncode == 2
    assert json.loads(path.read_text(encoding="utf-8"))["canonical"]["rows"][0]["option_slug"]


def test_snapshot_command_fails_closed_without_selector(taxonomy, tmp_path):
    with pytest.raises(CommandError) as exc_info:
        _snapshot(tmp_path, "a.json")
    assert exc_info.value.returncode == 2


# --- команда отката ---


def test_rollback_dry_run_does_not_write(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1")
    before, _ = _snapshot(tmp_path, "before.json", product_ids=str(p1.id))
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after, _ = _snapshot(tmp_path, "after.json", product_ids=str(p1.id))

    out = _rollback(after, before)

    assert "dry-run" in out
    assert "write=1" in out
    assert ProductAttributeValue.objects.filter(product=p1).exists()


def test_rollback_apply_restores_and_passes_post_audit(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1")
    before, _ = _snapshot(tmp_path, "before.json", product_ids=str(p1.id))
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Буры"})
    after, _ = _snapshot(tmp_path, "after.json", product_ids=str(p1.id))

    out = _rollback(after, before, apply=True)

    assert "post-audit=PASS" in out
    assert not ProductAttributeValue.objects.filter(product=p1).exists()


def test_rollback_conflict_exits_1_and_writes_nothing(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1")
    before, _ = _snapshot(tmp_path, "before.json", product_ids=str(p1.id))
    ProductAttributeValue.objects.create(
        product=p1, attribute=attribute, value_option=options["bury"]
    )
    after, _ = _snapshot(tmp_path, "after.json", product_ids=str(p1.id))
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["koronki"])

    with pytest.raises(CommandError) as exc_info:
        _rollback(after, before, apply=True)

    assert exc_info.value.returncode == 1
    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "koronki"


def test_rollback_invalid_artifact_exits_2(taxonomy, tmp_path):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before, _ = _snapshot(tmp_path, "before.json", product_ids=str(p1.id))
    after, _ = _snapshot(tmp_path, "after.json", product_ids=str(p1.id))
    doc = json.loads(before.read_text(encoding="utf-8"))
    doc["canonical"]["rows"][0]["option_slug"] = "koronki"
    before.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CommandError) as exc_info:
        _rollback(after, before)

    assert exc_info.value.returncode == 2


def test_rollback_missing_artifact_exits_2(taxonomy, tmp_path):
    p1 = _product("p1")
    before, _ = _snapshot(tmp_path, "before.json", product_ids=str(p1.id))

    with pytest.raises(CommandError) as exc_info:
        _rollback(tmp_path / "нет.json", before)

    assert exc_info.value.returncode == 2


# --- команда понижения версии ---


def _manifest(tmp_path, name, options, version):
    from apps.catalog.taxonomy_manifest import manifest_semantic_hash, taxonomy_identity_hash

    doc = {
        "schema_version": 1,
        "manifest_version": version,
        "attribute_slug": "tool_type",
        "status": "canonical",
        "semantic_duplicate_allowlist": [],
        "options": options,
    }
    doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def downgrade_pair(tmp_path):
    v2 = _manifest(
        tmp_path,
        "v2.json",
        [
            {"slug": "bury", "value": "Буры", "sort_order": 0},
            {"slug": "koronki", "value": "Коронки", "sort_order": 0},
        ],
        2,
    )
    v1 = _manifest(tmp_path, "v1.json", [{"slug": "bury", "value": "Буры", "sort_order": 0}], 1)
    call_command("load_tool_types", manifest=v2)
    return v2, v1


def _downgrade(v2, v1, **kwargs):
    buf = StringIO()
    call_command(
        "catalog_taxonomy_downgrade",
        from_manifest=v2,
        to_manifest=v1,
        stdout=buf,
        **kwargs,
    )
    return buf.getvalue()


def test_downgrade_plan_is_read_only_and_reports_drop(downgrade_pair, tmp_path):
    v2, v1 = downgrade_pair

    out = _downgrade(v2, v1, out=str(tmp_path / "plan.json"))

    assert "feasible=True" in out
    assert "drop=1" in out
    assert AttributeOption.objects.filter(slug="koronki").exists()
    assert json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))["canonical"]["feasible"]


def test_downgrade_blocked_plan_exits_1(downgrade_pair):
    v2, v1 = downgrade_pair
    attribute = Attribute.objects.get(slug="tool_type")
    _product("p1", option=AttributeOption.objects.get(slug="koronki"), attribute=attribute)

    with pytest.raises(CommandError) as exc_info:
        _downgrade(v2, v1)

    assert exc_info.value.returncode == 1
    assert "понижение не исполнимо" in str(exc_info.value)


def test_downgrade_apply_drop_requires_apply_flag(downgrade_pair):
    v2, v1 = downgrade_pair

    out = _downgrade(v2, v1, drop_options=True)

    assert "would_drop=['koronki']" in out
    assert AttributeOption.objects.filter(slug="koronki").exists()


def test_downgrade_apply_drop_removes_unused_option(downgrade_pair):
    v2, v1 = downgrade_pair

    out = _downgrade(v2, v1, drop_options=True, apply=True)

    assert "dropped=['koronki']" in out
    assert not AttributeOption.objects.filter(slug="koronki").exists()


def test_downgrade_emits_snapshot_pair_for_remap(downgrade_pair, tmp_path):
    v2, v1 = downgrade_pair
    attribute = Attribute.objects.get(slug="tool_type")
    p1 = _product("p1", option=AttributeOption.objects.get(slug="koronki"), attribute=attribute)
    remap = tmp_path / "remap.json"
    remap.write_text(json.dumps({"koronki": "bury"}), encoding="utf-8")

    _downgrade(
        v2,
        v1,
        remap=str(remap),
        emit_from=str(tmp_path / "from.json"),
        emit_to=str(tmp_path / "to.json"),
    )

    to_doc = json.loads((tmp_path / "to.json").read_text(encoding="utf-8"))
    assert to_doc["canonical"]["rows"] == [
        {
            "product_id": p1.id,
            "option_slug": "bury",
            "option_value": "Буры",
            "attrs_cache_tool_type": "Буры",
        }
    ]
    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "koronki"


def test_downgrade_rejects_manifest_version_gap(tmp_path):
    v3 = _manifest(tmp_path, "v3.json", [{"slug": "bury", "value": "Буры", "sort_order": 0}], 3)
    v1 = _manifest(tmp_path, "v1.json", [{"slug": "bury", "value": "Буры", "sort_order": 0}], 1)

    with pytest.raises(CommandError) as exc_info:
        _downgrade(v3, v1)

    assert exc_info.value.returncode == 2
