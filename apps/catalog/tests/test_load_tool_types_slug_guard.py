"""Seed-валидация load_tool_types против canonical taxonomy manifest (Wave 7.1/H1).

Раньше guard проверял seed-файл tool_type_rules.json; теперь источник options —
manifest: fail-closed на несовместимый slug/value, идемпотентность, no-delete,
--update-display только для sort_order.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import AttributeOption
from apps.catalog.taxonomy_manifest import manifest_semantic_hash, taxonomy_identity_hash


def _opt(slug, value, sort_order=0):
    return {"slug": slug, "value": value, "sort_order": sort_order}


def _manifest_file(tmp_path, options, name="manifest.json", **overrides):
    doc = {
        "schema_version": 1,
        "manifest_version": 1,
        "attribute_slug": "tool_type",
        "status": "canonical",
        "semantic_duplicate_allowlist": [],
        "options": options,
    }
    doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
    # overrides — после вычисления hashes (tamper-сценарии)
    doc.update(overrides)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _tt_options():
    return AttributeOption.objects.filter(attribute__slug="tool_type")


@pytest.mark.django_db
def test_clean_seed_creates_exact_manifest(tmp_path):
    path = _manifest_file(
        tmp_path, [_opt("a-slug", "А", 3), _opt("b-slug", "Б", 7), _opt("c-slug", "В", 1)]
    )
    call_command("load_tool_types", manifest=path)
    assert _tt_options().count() == 3
    opt = _tt_options().get(slug="b-slug")
    assert opt.value == "Б" and opt.sort_order == 7


@pytest.mark.django_db
def test_second_run_is_noop(tmp_path):
    path = _manifest_file(tmp_path, [_opt("a-slug", "А"), _opt("b-slug", "Б")])
    call_command("load_tool_types", manifest=path)
    created = call_command("load_tool_types", manifest=path)
    assert created == "0"
    assert _tt_options().count() == 2


@pytest.mark.django_db
def test_missing_option_created_present_untouched(tmp_path):
    path = _manifest_file(tmp_path, [_opt("a-slug", "А"), _opt("b-slug", "Б")])
    call_command("load_tool_types", manifest=path)
    _tt_options().get(slug="b-slug").delete()
    created = call_command("load_tool_types", manifest=path)
    assert created == "1"
    assert _tt_options().count() == 2


@pytest.mark.django_db
def test_incompatible_slug_value_fails_closed(tmp_path):
    path = _manifest_file(tmp_path, [_opt("a-slug", "Новое значение")])
    call_command(
        "load_tool_types", manifest=_manifest_file(tmp_path / "m2", [_opt("a-slug", "Старое")])
    )
    with pytest.raises(CommandError, match="option slug conflicts with DB"):
        call_command("load_tool_types", manifest=path)


@pytest.mark.django_db
def test_manifest_value_existing_under_other_slug_fails_closed(tmp_path):
    call_command(
        "load_tool_types", manifest=_manifest_file(tmp_path / "m1", [_opt("y-slug", "Значение")])
    )
    path = _manifest_file(tmp_path, [_opt("z-slug", "Значение")])
    with pytest.raises(CommandError, match="incompatible slug/value mapping"):
        call_command("load_tool_types", manifest=path)


@pytest.mark.django_db
def test_duplicate_slug_in_manifest_rejected(tmp_path):
    path = _manifest_file(tmp_path, [_opt("a-slug", "А"), _opt("a-slug", "Б")])
    with pytest.raises(CommandError, match="duplicate slug"):
        call_command("load_tool_types", manifest=path)


@pytest.mark.django_db
def test_tampered_identity_hash_rejected(tmp_path):
    path = _manifest_file(tmp_path, [_opt("a-slug", "А")], taxonomy_identity_hash="0" * 64)
    with pytest.raises(CommandError, match="taxonomy_identity_hash"):
        call_command("load_tool_types", manifest=path)


@pytest.mark.django_db
def test_sort_order_updated_only_with_flag(tmp_path):
    call_command(
        "load_tool_types", manifest=_manifest_file(tmp_path / "m1", [_opt("a-slug", "А", 5)])
    )
    path = _manifest_file(tmp_path, [_opt("a-slug", "А", 7)])
    call_command("load_tool_types", manifest=path)
    assert _tt_options().get(slug="a-slug").sort_order == 5
    call_command("load_tool_types", manifest=path, update_display=True)
    assert _tt_options().get(slug="a-slug").sort_order == 7


@pytest.mark.django_db
def test_nothing_deleted(tmp_path):
    call_command(
        "load_tool_types",
        manifest=_manifest_file(tmp_path / "m1", [_opt("a-slug", "А"), _opt("extra", "Лишний")]),
    )
    path = _manifest_file(tmp_path, [_opt("a-slug", "А")])
    call_command("load_tool_types", manifest=path)
    assert _tt_options().filter(slug="extra").exists()
