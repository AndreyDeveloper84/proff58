"""Runtime guard'ы taxonomy (Wave 7.1/H1): enrich_tool_type и backfill_option_slugs.

Создание AttributeOption(tool_type) в runtime возможно только из canonical
manifest; значения вне manifest — fail-closed (enrich) или advisory-пропуск
(backfill). Extraction-логика не меняется.
"""

from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError

from apps.catalog.management.commands.backfill_option_slugs import (
    Command as BackfillCommand,
)
from apps.catalog.management.commands.enrich_tool_type import Command as EnrichCommand
from apps.catalog.models import Attribute, AttributeOption, AttributeType
from apps.catalog.taxonomy_manifest import load_options_index

TOOL_TYPE = "tool_type"
MANIFEST_SLUG = "sterzhni-kleevye"
MANIFEST_VALUE = "Клеевые стержни"


@pytest.fixture
def attribute(db):
    return Attribute.objects.create(
        slug=TOOL_TYPE, name="Тип инструмента", attribute_type=AttributeType.SELECT
    )


@pytest.fixture
def manifest_options():
    return load_options_index()


def _ex(slug="", tool_type=""):
    return SimpleNamespace(slug=slug, tool_type=tool_type)


# --- enrich_tool_type._resolve_option ---


@pytest.mark.django_db
def test_resolve_returns_existing_by_slug(attribute, manifest_options):
    opt = AttributeOption.objects.create(attribute=attribute, slug="x-slug", value="X")
    cmd = EnrichCommand()
    result = cmd._resolve_option(
        attribute, _ex(slug="x-slug", tool_type="X"), {"x-slug": opt}, {}, manifest_options
    )
    assert result == opt


@pytest.mark.django_db
def test_resolve_returns_existing_by_normalized_value(attribute, manifest_options):
    from apps.catalog.tool_type import normalize

    opt = AttributeOption.objects.create(attribute=attribute, slug="x-slug", value="X Value")
    cmd = EnrichCommand()
    result = cmd._resolve_option(
        attribute,
        _ex(slug="", tool_type="X Value"),
        {},
        {normalize("X Value"): opt},
        manifest_options,
    )
    assert result == opt


@pytest.mark.django_db
def test_resolve_creates_from_manifest_by_slug(attribute, manifest_options):
    cmd = EnrichCommand()
    result = cmd._resolve_option(
        attribute, _ex(slug=MANIFEST_SLUG, tool_type=MANIFEST_VALUE), {}, {}, manifest_options
    )
    assert result.slug == MANIFEST_SLUG
    assert result.value == MANIFEST_VALUE
    mopt = manifest_options.by_slug(MANIFEST_SLUG)
    assert result.sort_order == mopt.sort_order


@pytest.mark.django_db
def test_resolve_creates_from_manifest_by_normalized_value(attribute, manifest_options):
    cmd = EnrichCommand()
    result = cmd._resolve_option(
        attribute, _ex(slug="", tool_type=MANIFEST_VALUE), {}, {}, manifest_options
    )
    assert result.slug == MANIFEST_SLUG


@pytest.mark.django_db
def test_resolve_outside_manifest_fails_closed(attribute, manifest_options):
    cmd = EnrichCommand()
    with pytest.raises(CommandError, match="option_not_in_manifest"):
        cmd._resolve_option(
            attribute,
            _ex(slug="", tool_type="Несуществующий тип инструмента"),
            {},
            {},
            manifest_options,
        )
    assert AttributeOption.objects.count() == 0


# --- backfill_option_slugs guard ---


class _FakeValuesQS:
    """Заглушка queryset-цепочки visible_products().annotate().filter().values_list().distinct()."""

    def __init__(self, values):
        self._values = values

    def annotate(self, **kwargs):
        return self

    def filter(self, **kwargs):
        return self

    def values_list(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def __iter__(self):
        return iter(self._values)


def _run_backfill(attribute, manifest_options, values, monkeypatch, dry_run=True):
    monkeypatch.setattr(
        "apps.catalog.management.commands.backfill_option_slugs.visible_products",
        lambda: _FakeValuesQS(values),
    )
    totals = {
        "scanned": 0,
        "created": 0,
        "filled": 0,
        "collisions": 0,
        "already": 0,
        "skipped_empty": 0,
        "missing_in_db": 0,
        "outside_manifest": 0,
    }
    BackfillCommand()._process_attribute(attribute, dry_run, totals, manifest_options)
    return totals


@pytest.mark.django_db
def test_backfill_does_not_create_outside_manifest(attribute, manifest_options, monkeypatch):
    totals = _run_backfill(attribute, manifest_options, ["Нестандартное значение"], monkeypatch)
    assert totals["outside_manifest"] == 1
    assert totals["created"] == 0
    assert AttributeOption.objects.count() == 0


@pytest.mark.django_db
def test_backfill_reports_manifest_option_missing_in_db(attribute, manifest_options, monkeypatch):
    totals = _run_backfill(attribute, manifest_options, [MANIFEST_VALUE], monkeypatch)
    assert totals["missing_in_db"] == 1
    assert totals["created"] == 0
    assert AttributeOption.objects.count() == 0


@pytest.mark.django_db
def test_backfill_existing_option_slug_fill_preserved(attribute, manifest_options, monkeypatch):
    opt = AttributeOption.objects.create(attribute=attribute, slug="", value="Пустослаговое")
    totals = _run_backfill(
        attribute, manifest_options, ["Пустослаговое"], monkeypatch, dry_run=False
    )
    opt.refresh_from_db()
    assert totals["filled"] == 1
    assert opt.slug
