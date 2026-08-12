"""Тесты reverse-map манифеста taxonomy: переход N → N-1 (Wave 7.1 / Stage H5)."""

import json

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Product,
    ProductAttributeValue,
)
from apps.catalog.taxonomy_manifest import manifest_semantic_hash, taxonomy_identity_hash
from apps.catalog.taxonomy_reverse import (
    REVERSE_SCHEMA_VERSION,
    ReverseMigrationError,
    build_downgrade_plan,
    diff_manifests,
    drop_disappearing_options,
    plan_bytes,
    snapshot_pair_for_remap,
)
from apps.catalog.tool_type_rollback import apply_rollback, plan_rollback

pytestmark = pytest.mark.django_db


def _opt(slug, value, sort_order=0, **kw):
    base = {"slug": slug, "value": value, "sort_order": sort_order}
    base.update(kw)
    return base


def _manifest_file(tmp_path, options, name, *, manifest_version=1):
    doc = {
        "schema_version": 1,
        "manifest_version": manifest_version,
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


V1 = [_opt("bury", "Буры"), _opt("sverla", "Свёрла")]
V2 = [_opt("bury", "Буры"), _opt("sverla", "Свёрла"), _opt("koronki", "Коронки")]


@pytest.fixture
def manifests(tmp_path):
    """Пара манифестов: v2 (текущий) добавил ``koronki`` поверх v1."""
    return (
        _manifest_file(tmp_path, V2, "v2.json", manifest_version=2),
        _manifest_file(tmp_path, V1, "v1.json", manifest_version=1),
    )


@pytest.fixture
def live_v2(manifests):
    """Живой словарь приведён к v2 штатным seed'ом."""
    call_command("load_tool_types", manifest=manifests[0])
    return manifests


def _product(slug, option_slug=None):
    product = Product.objects.create(slug=slug, original_name=slug, name=slug)
    if option_slug:
        attribute = Attribute.objects.get(slug="tool_type")
        option = AttributeOption.objects.get(attribute=attribute, slug=option_slug)
        ProductAttributeValue.objects.create(
            product=product, attribute=attribute, value_option=option
        )
        product.attrs_cache = {"tool_type": option.value}
        product.save(update_fields=["attrs_cache"])
    return product


# --- диффы манифестов ---


def test_diff_classifies_disappearing_reappearing_and_value_changed(tmp_path):
    new = _manifest_file(
        tmp_path,
        [_opt("bury", "Буры"), _opt("koronki", "Коронки"), _opt("sverla", "Свёрла v2")],
        "new.json",
        manifest_version=2,
    )
    old = _manifest_file(
        tmp_path,
        [_opt("bury", "Буры"), _opt("metchiki", "Метчики"), _opt("sverla", "Свёрла")],
        "old.json",
    )

    diff = diff_manifests(new, old)

    assert diff["unchanged"] == ["bury"]
    assert diff["disappearing"] == ["koronki"]
    assert diff["reappearing"] == ["metchiki"]
    assert diff["value_changed"] == ["sverla"]


# --- структурные fail-closed проверки ---


def test_plan_rejects_non_adjacent_manifest_version(tmp_path):
    new = _manifest_file(tmp_path, V2, "v3.json", manifest_version=3)
    old = _manifest_file(tmp_path, V1, "v1.json", manifest_version=1)

    with pytest.raises(ReverseMigrationError, match="N → N-1"):
        build_downgrade_plan(from_manifest=new, to_manifest=old)


def test_plan_rejects_forward_direction(tmp_path):
    new = _manifest_file(tmp_path, V1, "v1.json", manifest_version=1)
    old = _manifest_file(tmp_path, V2, "v2.json", manifest_version=2)

    with pytest.raises(ReverseMigrationError, match="N → N-1"):
        build_downgrade_plan(from_manifest=new, to_manifest=old)


def test_plan_blocks_when_live_taxonomy_is_not_at_from_manifest(manifests):
    plan = build_downgrade_plan(from_manifest=manifests[0], to_manifest=manifests[1])

    assert plan.feasible is False
    assert [b["code"] for b in plan.blocking] == ["live_not_at_from_manifest"]


# --- решения по опциям ---


def test_disappearing_option_without_products_is_dropped(live_v2):
    plan = build_downgrade_plan(from_manifest=live_v2[0], to_manifest=live_v2[1])

    entry = next(e for e in plan.entries if e["slug"] == "koronki")
    assert entry["disposition"] == "drop"
    assert entry["pav_count"] == 0
    assert plan.feasible is True


def test_disappearing_option_with_products_blocks_without_remap(live_v2):
    _product("p1", "koronki")

    plan = build_downgrade_plan(from_manifest=live_v2[0], to_manifest=live_v2[1])

    entry = next(e for e in plan.entries if e["slug"] == "koronki")
    assert entry["disposition"] == "blocked"
    assert entry["pav_count"] == 1
    assert plan.feasible is False
    assert plan.blocking[0]["code"] == "orphaned_products"


def test_explicit_remap_makes_downgrade_feasible(live_v2):
    _product("p1", "koronki")

    plan = build_downgrade_plan(
        from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "sverla"}
    )

    entry = next(e for e in plan.entries if e["slug"] == "koronki")
    assert entry["disposition"] == "remap"
    assert entry["remap_to"] == "sverla"
    assert plan.feasible is True
    assert plan.summary["affected_products"] == 1


def test_remap_target_absent_in_target_manifest_blocks(live_v2):
    _product("p1", "koronki")

    plan = build_downgrade_plan(
        from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "neizvestno"}
    )

    assert plan.feasible is False
    assert plan.blocking[0]["code"] == "remap_target_unknown"


def test_remap_for_surviving_slug_is_rejected(live_v2):
    with pytest.raises(ReverseMigrationError, match="не исчезает"):
        build_downgrade_plan(
            from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"bury": "sverla"}
        )


def test_value_change_between_manifests_blocks_as_manual(tmp_path):
    new = _manifest_file(
        tmp_path, [_opt("bury", "Буры"), _opt("sverla", "Свёрла")], "v2.json", manifest_version=2
    )
    old = _manifest_file(tmp_path, [_opt("bury", "Буры"), _opt("sverla", "Сверла")], "v1.json")
    call_command("load_tool_types", manifest=new)

    plan = build_downgrade_plan(from_manifest=new, to_manifest=old)

    entry = next(e for e in plan.entries if e["slug"] == "sverla")
    assert entry["disposition"] == "blocked"
    assert plan.blocking[0]["code"] == "value_change_requires_manual"


def test_reappearing_option_is_reported_as_seed_step(tmp_path):
    new = _manifest_file(tmp_path, [_opt("bury", "Буры")], "v2.json", manifest_version=2)
    old = _manifest_file(tmp_path, [_opt("bury", "Буры"), _opt("metchiki", "Метчики")], "v1.json")
    call_command("load_tool_types", manifest=new)

    plan = build_downgrade_plan(from_manifest=new, to_manifest=old)

    entry = next(e for e in plan.entries if e["slug"] == "metchiki")
    assert entry["disposition"] == "reappearing"
    assert plan.feasible is True
    assert plan.summary["reappearing"] == 1


# --- сам план read-only и байт-стабилен ---


def test_plan_document_is_byte_stable(live_v2):
    _product("p1", "koronki")
    kwargs = dict(from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "sverla"})

    first = plan_bytes(build_downgrade_plan(**kwargs).document)
    second = plan_bytes(build_downgrade_plan(**kwargs).document)

    assert first == second
    assert json.loads(first)["canonical"]["schema_version"] == REVERSE_SCHEMA_VERSION


def test_plan_writes_nothing_to_database(live_v2):
    _product("p1", "koronki")
    before = (
        AttributeOption.objects.count(),
        ProductAttributeValue.objects.count(),
        Product.objects.count(),
    )

    build_downgrade_plan(
        from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "sverla"}
    )

    assert (
        AttributeOption.objects.count(),
        ProductAttributeValue.objects.count(),
        Product.objects.count(),
    ) == before


# --- связка с исполнителем отката ---


def test_snapshot_pair_moves_products_to_remap_target(live_v2):
    p1 = _product("p1", "koronki")
    plan = build_downgrade_plan(
        from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "sverla"}
    )

    from_doc, to_doc = snapshot_pair_for_remap(plan)

    assert [r["option_slug"] for r in from_doc["canonical"]["rows"]] == ["koronki"]
    assert to_doc["canonical"]["rows"] == [
        {
            "product_id": p1.id,
            "option_slug": "sverla",
            "option_value": "Свёрла",
            "attrs_cache_tool_type": "Свёрла",
        }
    ]


def test_remap_executed_through_rollback_executor(live_v2):
    p1 = _product("p1", "koronki")
    plan = build_downgrade_plan(
        from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "sverla"}
    )

    apply_rollback(plan_rollback(*snapshot_pair_for_remap(plan)))

    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "sverla"
    assert Product.objects.get(id=p1.id).attrs_cache["tool_type"] == "Свёрла"


# --- удаление исчезнувших опций ---


def test_drop_dry_run_writes_nothing(live_v2):
    plan = build_downgrade_plan(from_manifest=live_v2[0], to_manifest=live_v2[1])

    result = drop_disappearing_options(plan, apply=False)

    assert result["would_drop"] == ["koronki"]
    assert result["dropped"] == []
    assert AttributeOption.objects.filter(slug="koronki").exists()


def test_drop_removes_only_disappearing_options_with_zero_usage(live_v2):
    _product("p1", "bury")
    plan = build_downgrade_plan(from_manifest=live_v2[0], to_manifest=live_v2[1])

    result = drop_disappearing_options(plan, apply=True)

    assert result["dropped"] == ["koronki"]
    assert not AttributeOption.objects.filter(slug="koronki").exists()
    assert AttributeOption.objects.filter(slug="bury").exists()
    assert AttributeOption.objects.filter(slug="sverla").exists()


def test_drop_is_idempotent(live_v2):
    plan = build_downgrade_plan(from_manifest=live_v2[0], to_manifest=live_v2[1])
    drop_disappearing_options(plan, apply=True)

    second = drop_disappearing_options(plan, apply=True)

    assert second["dropped"] == []
    assert second["already_absent"] == ["koronki"]


def test_drop_refuses_when_option_still_carries_products(live_v2):
    _product("p1", "koronki")
    plan = build_downgrade_plan(
        from_manifest=live_v2[0], to_manifest=live_v2[1], remap={"koronki": "sverla"}
    )

    with pytest.raises(ReverseMigrationError, match="товары"):
        drop_disappearing_options(plan, apply=True)

    assert AttributeOption.objects.filter(slug="koronki").exists()


def test_drop_refuses_infeasible_plan(live_v2):
    _product("p1", "koronki")
    plan = build_downgrade_plan(from_manifest=live_v2[0], to_manifest=live_v2[1])

    with pytest.raises(ReverseMigrationError, match="feasible"):
        drop_disappearing_options(plan, apply=True)
