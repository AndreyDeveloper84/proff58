"""Тесты catalog_taxonomy_reconcile (Wave 7.1/H1): blocking/advisory категории drift."""

import io
import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.management.commands.catalog_taxonomy_reconcile import Command
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Product,
    ProductAttributeValue,
)
from apps.catalog.taxonomy_manifest import manifest_semantic_hash, taxonomy_identity_hash


def _opt(slug, value, sort_order=0, **kw):
    base = {"slug": slug, "value": value, "sort_order": sort_order}
    base.update(kw)
    return base


def _manifest_file(tmp_path, options, name="manifest.json", **overrides):
    doc = {
        "schema_version": 1,
        "manifest_version": 1,
        "attribute_slug": "tool_type",
        "status": "canonical",
        "semantic_duplicate_allowlist": [],
        "options": options,
    }
    doc.update(overrides)
    doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _fake_ruleset(*slugs):
    return SimpleNamespace(rules=[SimpleNamespace(option_slug=s) for s in slugs])


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """Manifest из 3 options, применённый seed; ruleset замокан на подмножество."""
    path = _manifest_file(tmp_path, [_opt("a-slug", "А"), _opt("b-slug", "Б"), _opt("c-slug", "В")])
    call_command("load_tool_types", manifest=path)
    monkeypatch.setattr(
        "apps.catalog.management.commands.catalog_taxonomy_reconcile.load_ruleset",
        lambda path=None: _fake_ruleset("a-slug", "b-slug"),
    )
    return path


def _reconcile(path, **kwargs):
    out = io.StringIO()
    call_command("catalog_taxonomy_reconcile", manifest=path, stdout=out, **kwargs)
    return out.getvalue()


def _report(cmd, path, ruleset_path=None):
    from apps.catalog.taxonomy_manifest import load_manifest

    return cmd._build_report(load_manifest(path), ruleset_path)


@pytest.mark.django_db
def test_clean_state_no_drift(seeded):
    output = _reconcile(seeded)
    assert "identity_equal=True" in output
    report = _report(Command(), seeded)
    assert all(not v for v in report["blocking"].values())
    advisory = report["advisory"]
    # все 3 options свежего seed пока без товаров — ожидаемый advisory, не drift
    assert sorted(advisory["manifest_unused_option"]) == ["a-slug", "b-slug", "c-slug"]
    assert not advisory["semantic_duplicate"]
    assert not advisory["display_metadata_mismatch"]
    assert not advisory["pending_business_review"]


@pytest.mark.django_db
def test_missing_in_live_blocks(seeded):
    AttributeOption.objects.get(slug="b-slug").delete()
    with pytest.raises(CommandError, match="blocking drift"):
        _reconcile(seeded)


@pytest.mark.django_db
def test_unexpected_in_live_blocks(seeded):
    attr = Attribute.objects.get(slug="tool_type")
    AttributeOption.objects.create(attribute=attr, slug="d-slug", value="Г")
    with pytest.raises(CommandError, match="blocking drift"):
        _reconcile(seeded)


@pytest.mark.django_db
def test_slug_value_mismatch_blocks(seeded):
    opt = AttributeOption.objects.get(slug="a-slug")
    opt.value = "Изменённое"
    opt.save()
    with pytest.raises(CommandError, match="blocking drift"):
        _reconcile(seeded)


@pytest.mark.django_db
def test_used_outside_manifest_blocks(seeded):
    attr = Attribute.objects.get(slug="tool_type")
    extra = AttributeOption.objects.create(attribute=attr, slug="extra", value="Лишний")
    product = Product.objects.create(slug="p1", original_name="Товар 1")
    ProductAttributeValue.objects.create(attribute=attr, product=product, value_option=extra)
    report = _report(Command(), seeded)
    assert report["blocking"]["used_outside_manifest"] == [{"slug": "extra", "pav_count": 1}]
    with pytest.raises(CommandError, match="blocking drift"):
        _reconcile(seeded)


@pytest.mark.django_db
def test_ruleset_unknown_slug_blocks(seeded, monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.management.commands.catalog_taxonomy_reconcile.load_ruleset",
        lambda path=None: _fake_ruleset("a-slug", "unknown-slug"),
    )
    with pytest.raises(CommandError, match="blocking drift"):
        _reconcile(seeded)


@pytest.mark.django_db
def test_semantic_duplicate_advisory_only(tmp_path, monkeypatch):
    # (attribute, value) unique-constraint делает live-дубликат невозможным в БД —
    # детектор проверяется на синтетическом live-снимке (legacy-состояние до констрейнта).
    path = _manifest_file(
        tmp_path,
        [_opt("a-slug", "Дубль"), _opt("b-slug", "Дубль")],
        semantic_duplicate_allowlist=[["a-slug", "b-slug"]],
    )
    monkeypatch.setattr(
        "apps.catalog.management.commands.catalog_taxonomy_reconcile.load_ruleset",
        lambda path=None: _fake_ruleset("a-slug"),
    )
    from apps.catalog.taxonomy_manifest import load_manifest

    live = [
        SimpleNamespace(slug="a-slug", value="Дубль", sort_order=0, id=None),
        SimpleNamespace(slug="b-slug", value="Дубль", sort_order=1, id=None),
    ]
    report = Command()._build_report(load_manifest(path), None, live=live)
    assert report["advisory"]["semantic_duplicate"] == {"Дубль": ["a-slug", "b-slug"]}
    assert all(not v for v in report["blocking"].values())


@pytest.mark.django_db
def test_manifest_unused_option_advisory_only(seeded):
    report = _report(Command(), seeded)
    assert sorted(report["advisory"]["manifest_unused_option"]) == ["a-slug", "b-slug", "c-slug"]
    _reconcile(seeded)  # unused options не роняют blocking
    with pytest.raises(CommandError, match="advisory findings"):
        _reconcile(seeded, fail_on="any")


@pytest.mark.django_db
def test_display_metadata_mismatch_advisory_only(seeded):
    opt = AttributeOption.objects.get(slug="a-slug")
    opt.sort_order = 99
    opt.save()
    report = _report(Command(), seeded)
    assert report["advisory"]["display_metadata_mismatch"] == ["a-slug"]
    _reconcile(seeded)


@pytest.mark.django_db
def test_pending_business_review_advisory(tmp_path, monkeypatch):
    path = _manifest_file(
        tmp_path,
        [
            _opt("a-slug", "А"),
            _opt("b-slug", "Б", review_status="pending_business_review"),
        ],
    )
    call_command("load_tool_types", manifest=path)
    monkeypatch.setattr(
        "apps.catalog.management.commands.catalog_taxonomy_reconcile.load_ruleset",
        lambda path=None: _fake_ruleset("a-slug"),
    )
    report = _report(Command(), path)
    assert report["advisory"]["pending_business_review"] == ["b-slug"]
    _reconcile(path)
