"""Негативная матрица H5: каждый guard контура отката проверяется отдельно.

Испорченные артефакты создаются только во временных каталогах (``tmp_path``).
Ни один сценарий не должен приводить к записи в БД.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Product,
    ProductAttributeValue,
)
from apps.catalog.rules_release import canonical_hash_of
from apps.catalog.taxonomy_manifest import manifest_semantic_hash, taxonomy_identity_hash
from apps.catalog.taxonomy_reverse import (
    ReverseMigrationError,
    build_downgrade_plan,
    drop_disappearing_options,
    snapshot_pair_for_remap,
)
from apps.catalog.tool_type_rollback import (
    RollbackError,
    apply_rollback,
    build_snapshot,
    load_snapshot,
    plan_rollback,
    validate_snapshot,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def taxonomy():
    attribute = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    options = {
        slug: AttributeOption.objects.create(attribute=attribute, slug=slug, value=value)
        for slug, value in (("bury", "Буры"), ("sverla", "Свёрла"))
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


def _reseal(canonical):
    return {"canonical": canonical, "canonical_hash": canonical_hash_of(canonical)}


# --- 1. структура снимка ---


def test_snapshot_with_foreign_attribute_slug_is_rejected(taxonomy):
    p1 = _product("p1")
    doc = build_snapshot(product_ids=[p1.id])
    doc = _reseal({**doc["canonical"], "attribute_slug": "brand"})

    with pytest.raises(RollbackError, match="не по атрибуту"):
        validate_snapshot(doc)


def test_snapshot_with_unsupported_schema_version_is_rejected(taxonomy):
    p1 = _product("p1")
    doc = build_snapshot(product_ids=[p1.id])
    doc = _reseal({**doc["canonical"], "schema_version": 99})

    with pytest.raises(RollbackError, match="schema_version"):
        validate_snapshot(doc)


def test_snapshot_with_duplicate_product_rows_is_rejected(taxonomy):
    p1 = _product("p1")
    doc = build_snapshot(product_ids=[p1.id])
    rows = doc["canonical"]["rows"] * 2
    doc = _reseal({**doc["canonical"], "rows": rows, "rows_count": 2})

    with pytest.raises(RollbackError, match="дубликаты product_id"):
        validate_snapshot(doc)


def test_snapshot_with_wrong_rows_count_is_rejected(taxonomy):
    p1 = _product("p1")
    doc = build_snapshot(product_ids=[p1.id])
    doc = _reseal({**doc["canonical"], "rows_count": 7})

    with pytest.raises(RollbackError, match="rows_count"):
        validate_snapshot(doc)


def test_snapshot_without_canonical_section_is_rejected():
    with pytest.raises(RollbackError, match="нет секции canonical"):
        validate_snapshot({"rows": []})


def test_snapshot_file_with_broken_json_is_rejected(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{не json", encoding="utf-8")

    with pytest.raises(RollbackError, match="не валидный JSON"):
        load_snapshot(path)


def test_snapshot_selector_with_unknown_option_slug_is_rejected(taxonomy):
    with pytest.raises(RollbackError, match="нет в live-словаре"):
        build_snapshot(option_slugs=["neizvestno"])


def test_snapshot_with_two_selectors_is_rejected(taxonomy):
    p1 = _product("p1")

    with pytest.raises(RollbackError, match="ровно один селектор"):
        build_snapshot(product_ids=[p1.id], all_with_tool_type=True)


# --- 2. гонки между планом и применением ---


def test_product_deleted_between_plan_and_apply_aborts_write(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    p2 = _product("p2", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id, p2.id])
    ProductAttributeValue.objects.filter(product__in=[p1, p2]).update(
        value_option=options["sverla"]
    )
    after = build_snapshot(product_ids=[p1.id, p2.id])
    plan = plan_rollback(after, before)
    Product.objects.filter(id=p1.id).delete()

    with pytest.raises(RollbackError, match="исчез между планом и применением"):
        apply_rollback(plan)

    assert ProductAttributeValue.objects.get(product=p2).value_option.slug == "sverla"


def test_option_deleted_between_plan_and_apply_aborts_write(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    before = build_snapshot(product_ids=[p1.id])
    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["sverla"])
    after = build_snapshot(product_ids=[p1.id])
    plan = plan_rollback(after, before)
    AttributeOption.objects.filter(slug="bury").delete()

    with pytest.raises(RollbackError, match="исчез между планом и применением"):
        apply_rollback(plan)

    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "sverla"


# --- 2b. baseline изменился между планом и применением (H6) ---
#
# plan_rollback читает live вне транзакции записи. Если между планом и apply
# чужой процесс поменял tool_type, применение обязано увидеть это внутри своей
# транзакции и отказать целиком, а не молча перезаписать чужое изменение.


def _forward_pair(attribute, options, products):
    """Пара снимков «до»/«после» для отката products с sverla обратно на bury."""
    ids = [p.id for p in products]
    before = build_snapshot(product_ids=ids)
    ProductAttributeValue.objects.filter(product_id__in=ids).update(value_option=options["sverla"])
    Product.objects.filter(id__in=ids).update(attrs_cache={"tool_type": "Свёрла"})
    after = build_snapshot(product_ids=ids)
    return after, before


def test_baseline_changed_between_plan_and_apply_aborts_whole_write(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    p2 = _product("p2", option=options["bury"], attribute=attribute, cache_value="Буры")
    after, before = _forward_pair(attribute, options, [p1, p2])
    plan = plan_rollback(after, before)
    assert plan.counts["write"] == 2

    # чужая запись между планом и применением — только по p1
    koronki = AttributeOption.objects.create(attribute=attribute, slug="koronki", value="Коронки")
    ProductAttributeValue.objects.filter(product=p1).update(value_option=koronki)

    with pytest.raises(RollbackError, match="baseline изменился между планом и применением"):
        apply_rollback(plan)

    # чужое изменение уцелело, а p2 не откачен: план не применён целиком
    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "koronki"
    assert ProductAttributeValue.objects.get(product=p2).value_option.slug == "sverla"


def test_pav_removed_between_plan_and_apply_aborts_write(taxonomy):
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    after, before = _forward_pair(attribute, options, [p1])
    plan = plan_rollback(after, before)

    ProductAttributeValue.objects.filter(product=p1).delete()

    with pytest.raises(RollbackError, match="baseline изменился между планом и применением"):
        apply_rollback(plan)

    assert not ProductAttributeValue.objects.filter(product=p1).exists()


def test_concurrent_rollback_to_same_target_is_counted_as_noop(taxonomy):
    """Чужой процесс уже откатил товар на цель — это не conflict, а идемпотентность."""
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    after, before = _forward_pair(attribute, options, [p1])
    plan = plan_rollback(after, before)

    ProductAttributeValue.objects.filter(product=p1).update(value_option=options["bury"])
    Product.objects.filter(id=p1.id).update(attrs_cache={"tool_type": "Буры"})

    stats = apply_rollback(plan)

    assert stats == {"written": 0, "noop": 1}
    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == "bury"


def test_apply_locks_product_and_pav_rows(taxonomy):
    """Повторная сверка обязана идти под блокировкой, иначе окно гонки остаётся."""
    attribute, options = taxonomy
    p1 = _product("p1", option=options["bury"], attribute=attribute, cache_value="Буры")
    after, before = _forward_pair(attribute, options, [p1])
    plan = plan_rollback(after, before)

    with CaptureQueriesContext(connection) as captured:
        apply_rollback(plan)

    # «Блокируй, потом смотри»: первое же обращение apply к каждой из таблиц
    # обязано быть FOR UPDATE, иначе повторная сверка читает незалоченные строки
    # и окно гонки остаётся открытым.
    for table in ("catalog_product", "catalog_productattributevalue"):
        touching = [q["sql"] for q in captured.captured_queries if f'FROM "{table}"' in q["sql"]]
        assert touching, f"apply не обращался к {table}"
        assert "FOR UPDATE" in touching[0].upper(), touching[0]


# --- 3. reverse-map: remap-цели ---


def _manifest(tmp_path, name, options, version):
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


def _opt(slug, value):
    return {"slug": slug, "value": value, "sort_order": 0}


@pytest.fixture
def two_disappearing(tmp_path):
    """v2 добавил ``koronki`` и ``adaptery``; обе исчезают при понижении."""
    v2 = _manifest(
        tmp_path,
        "v2.json",
        [_opt("bury", "Буры"), _opt("koronki", "Коронки"), _opt("adaptery", "Адаптеры")],
        2,
    )
    v1 = _manifest(tmp_path, "v1.json", [_opt("bury", "Буры")], 1)
    call_command("load_tool_types", manifest=v2)
    return v2, v1


def test_remap_to_option_that_also_disappears_is_blocked(two_disappearing):
    v2, v1 = two_disappearing
    attribute = Attribute.objects.get(slug="tool_type")
    _product("p1", option=AttributeOption.objects.get(slug="koronki"), attribute=attribute)

    plan = build_downgrade_plan(from_manifest=v2, to_manifest=v1, remap={"koronki": "adaptery"})

    assert plan.feasible is False
    assert plan.blocking[0]["code"] == "remap_target_disappearing"


def test_remap_to_option_absent_in_live_is_blocked(tmp_path):
    v2 = _manifest(tmp_path, "v2.json", [_opt("bury", "Буры"), _opt("koronki", "Коронки")], 2)
    v1 = _manifest(tmp_path, "v1.json", [_opt("bury", "Буры"), _opt("sverla", "Свёрла")], 1)
    call_command("load_tool_types", manifest=v2)
    attribute = Attribute.objects.get(slug="tool_type")
    _product("p1", option=AttributeOption.objects.get(slug="koronki"), attribute=attribute)

    plan = build_downgrade_plan(from_manifest=v2, to_manifest=v1, remap={"koronki": "sverla"})

    assert plan.feasible is False
    assert plan.blocking[0]["code"] == "remap_target_not_live"


def test_manifests_for_different_attributes_are_rejected(tmp_path):
    v2 = _manifest(tmp_path, "v2.json", [_opt("bury", "Буры")], 2)
    other = json.loads((tmp_path / "v2.json").read_text(encoding="utf-8"))
    other["attribute_slug"] = "brand"
    other["manifest_version"] = 1
    other["manifest_semantic_hash"] = manifest_semantic_hash(other)
    path = tmp_path / "other.json"
    path.write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")

    with pytest.raises((ReverseMigrationError, ValueError), match="attribute|атрибут"):
        build_downgrade_plan(from_manifest=v2, to_manifest=str(path))


# --- 4. пара снимков ---


def test_snapshot_pair_refuses_infeasible_plan(two_disappearing):
    v2, v1 = two_disappearing
    attribute = Attribute.objects.get(slug="tool_type")
    _product("p1", option=AttributeOption.objects.get(slug="koronki"), attribute=attribute)
    plan = build_downgrade_plan(from_manifest=v2, to_manifest=v1)

    with pytest.raises(ReverseMigrationError, match="не feasible"):
        snapshot_pair_for_remap(plan)


def test_snapshot_pair_refuses_plan_without_remap_entries(two_disappearing):
    v2, v1 = two_disappearing
    plan = build_downgrade_plan(from_manifest=v2, to_manifest=v1)

    with pytest.raises(ReverseMigrationError, match="нет remap-записей"):
        snapshot_pair_for_remap(plan)


def test_drop_does_not_touch_options_outside_the_plan(two_disappearing):
    v2, v1 = two_disappearing
    before = set(AttributeOption.objects.values_list("slug", flat=True))
    plan = build_downgrade_plan(from_manifest=v2, to_manifest=v1)

    drop_disappearing_options(plan, apply=True)

    after = set(AttributeOption.objects.values_list("slug", flat=True))
    assert before - after == {"koronki", "adaptery"}
    assert after == {"bury"}


# --- 5. CLI-контракт ---


def _downgrade(**kwargs):
    buf = StringIO()
    call_command("catalog_taxonomy_downgrade", stdout=buf, **kwargs)
    return buf.getvalue()


def test_cli_emit_from_without_emit_to_is_rejected(two_disappearing, tmp_path):
    v2, v1 = two_disappearing

    with pytest.raises(CommandError) as exc_info:
        _downgrade(from_manifest=v2, to_manifest=v1, emit_from=str(tmp_path / "f.json"))

    assert exc_info.value.returncode == 2


def test_cli_remap_file_must_be_flat_string_mapping(two_disappearing, tmp_path):
    v2, v1 = two_disappearing
    bad = tmp_path / "remap.json"
    bad.write_text(json.dumps({"koronki": ["bury"]}), encoding="utf-8")

    with pytest.raises(CommandError) as exc_info:
        _downgrade(from_manifest=v2, to_manifest=v1, remap=str(bad))

    assert exc_info.value.returncode == 2


def test_cli_missing_remap_file_is_rejected(two_disappearing, tmp_path):
    v2, v1 = two_disappearing

    with pytest.raises(CommandError) as exc_info:
        _downgrade(from_manifest=v2, to_manifest=v1, remap=str(tmp_path / "нет.json"))

    assert exc_info.value.returncode == 2


def test_cli_downgrade_writes_nothing_when_plan_is_blocked(two_disappearing, tmp_path):
    v2, v1 = two_disappearing
    attribute = Attribute.objects.get(slug="tool_type")
    _product("p1", option=AttributeOption.objects.get(slug="koronki"), attribute=attribute)
    before = set(AttributeOption.objects.values_list("slug", flat=True))

    with pytest.raises(CommandError):
        _downgrade(from_manifest=v2, to_manifest=v1, drop_options=True, apply=True)

    assert set(AttributeOption.objects.values_list("slug", flat=True)) == before
