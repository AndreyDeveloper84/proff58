"""Taxonomy changeset ADR-0011: option ``dinamometricheskie-klyuchi``.

Покрытие контракта changeset'а:
- option присутствует в manifest (секция «Ручной инструмент») и в allowed_options
  после ``load_tool_types``;
- ``load_tool_types`` создаёт ровно одну новую option, повторный запуск — 0;
- существующие options сохраняют PK/slug/sort_order, новых дублей slug/value нет;
- новый ``CategoryAttribute`` не создаётся;
- ``match_keywords: []`` намеренно: legacy ``enrich_tool_type`` НЕ назначает новый
  slug даже для динамометрических ключей (текущий маршрут — ``klyuchi-gaechnye``;
  remediation 12957/12959 — отдельная операция по ADR-0011, здесь не выполняется);
- regression: существующий web PAV заменяется approved manual change через текущий
  CatalogChange/baseline/apply-сервис; before_value и audit сохраняются,
  посторонние поля не меняются.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.catalog import processing
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogChangeStatus,
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)
from apps.catalog.processing import canonical_hash, tool_type_snapshot
from apps.catalog.queue_contract import _allowed_tool_type_options
from apps.catalog.tool_type import ASSIGNED, ToolTypeRules

RULES_PATH = Path(settings.BASE_DIR) / "data" / "tool_type_rules.json"
NEW_SLUG = "dinamometricheskie-klyuchi"
NEW_VALUE = "Динамометрические ключи"
TOP_CATEGORY = "Ручной инструмент"


class ManifestTests(TestCase):
    """Новая option в manifest: секция, контракт и отсутствие новых дублей."""

    def setUp(self):
        self.rules = ToolTypeRules.from_file(RULES_PATH)

    def test_option_present_in_ruchnoy_section_with_empty_keywords(self):
        options = self.rules.options(TOP_CATEGORY)
        matched = [r for r in options if r.slug == NEW_SLUG]
        self.assertEqual(len(matched), 1)
        rule = matched[0]
        self.assertEqual(rule.tool_type, NEW_VALUE)
        # Пустые keywords намеренно: option только материализуется в словарь,
        # legacy extraction её не назначает (Phase 6.0 — отдельно).
        self.assertEqual(list(rule.match_keywords), [])

    def test_new_slug_and_value_are_unique_in_manifest(self):
        all_rules = [
            rule for cat in self.rules.categories for rule in self.rules.options(cat.category)
        ]
        self.assertEqual(sum(r.slug == NEW_SLUG for r in all_rules), 1)
        self.assertEqual(sum(r.tool_type == NEW_VALUE for r in all_rules), 1)

    def test_legacy_extraction_does_not_assign_new_slug(self):
        # Фиксируем текущее поведение: правило klyuchi-gaechnye содержит keywords
        # «ключ динамометр»/«динамометр», поэтому legacy маршрутизирует
        # динамометрические ключи в klyuchi-gaechnye. Это сознательный non-change:
        # keywords klyuchi-gaechnye не трогаем, remediation — по ADR-0011 отдельно.
        for name in (
            'Ключ динамометрический 1/2" 28-210 Нм',
            "Динамометрический ключ 3/8 5-25Нм",
        ):
            ex = self.rules.extract(TOP_CATEGORY, name)
            self.assertEqual(ex.result, ASSIGNED, name)
            self.assertEqual(ex.slug, "klyuchi-gaechnye", name)
            self.assertNotEqual(ex.slug, NEW_SLUG, name)


class LoadToolTypesDeltaTests(TestCase):
    """Delta changeset'а manifest: ровно одна новая option, без side effects (Wave 7.1/H1).

    «До» — canonical manifest без новой option; «changeset» — текущий canonical
    manifest (default). Существующие options: PK/slug/sort_order без изменений.
    """

    def setUp(self):
        Category.add_root(name=TOP_CATEGORY, slug="ruchnoy-instrument")

    def _snapshot_options(self, attr):
        return {
            opt.value: (opt.pk, opt.slug, opt.sort_order)
            for opt in AttributeOption.objects.filter(attribute=attr)
        }

    @staticmethod
    def _manifest_without(tmp_dir, exclude_slugs):
        from apps.catalog.taxonomy_manifest import (
            MANIFEST_PATH,
            manifest_semantic_hash,
            taxonomy_identity_hash,
        )

        doc = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        doc["options"] = [o for o in doc["options"] if o["slug"] not in exclude_slugs]
        doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
        doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
        path = Path(tmp_dir) / "manifest.json"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_changeset_creates_exactly_one_option_without_side_effects(self):
        # Seed состояния «до» — canonical manifest без новой option.
        with tempfile.TemporaryDirectory() as tmp:
            before_manifest = self._manifest_without(tmp, {NEW_SLUG})
            call_command("load_tool_types", manifest=before_manifest)

        attr = Attribute.objects.get(slug="tool_type")
        before = self._snapshot_options(attr)
        self.assertNotIn(NEW_VALUE, before)
        cat_attr_before = CategoryAttribute.objects.count()

        # --- Применяем changeset (текущий canonical manifest). ---
        created = call_command("load_tool_types")

        self.assertEqual(created, "1", "changeset должен создать ровно одну option")
        after = self._snapshot_options(attr)
        self.assertEqual(len(after), len(before) + 1)

        # Существующие options: PK/slug/sort_order без изменений.
        for value, identity in before.items():
            self.assertEqual(
                after.get(value), identity, f"изменилась существующая option {value!r}"
            )

        # Новая option: slug и sort_order — из canonical manifest.
        from apps.catalog.taxonomy_manifest import load_manifest

        expected = {o.slug: o for o in load_manifest().options}[NEW_SLUG]
        pk, slug, sort_order = after[NEW_VALUE]
        self.assertEqual(slug, NEW_SLUG)
        self.assertEqual(sort_order, expected.sort_order)

        # Дублей slug/value для новой option нет.
        self.assertEqual(AttributeOption.objects.filter(attribute=attr, slug=NEW_SLUG).count(), 1)
        self.assertEqual(AttributeOption.objects.filter(attribute=attr, value=NEW_VALUE).count(), 1)

        # Новый CategoryAttribute не создаётся (привязка «Ручной инструмент» уже была).
        self.assertEqual(CategoryAttribute.objects.count(), cat_attr_before)

        # option попадает в allowed_options export-контракта.
        allowed = {(o["slug"], o["value"]) for o in _allowed_tool_type_options()}
        self.assertIn((NEW_SLUG, NEW_VALUE), allowed)

        # Идемпотентность: повторный запуск создаёт 0.
        created_again = call_command("load_tool_types")
        self.assertEqual(created_again, "0")
        self.assertEqual(self._snapshot_options(attr), after)
        self.assertEqual(CategoryAttribute.objects.count(), cat_attr_before)


# --- Regression: existing web PAV → approved manual taxonomy correction (ADR-0011) ---


@pytest.fixture
def feature_enabled():
    old = settings.FEATURES.get("catalog_processing")
    settings.FEATURES["catalog_processing"] = True
    yield
    settings.FEATURES["catalog_processing"] = old


@pytest.fixture
def reviewer():
    return get_user_model().objects.create(phone="+79990000002")


@pytest.fixture
def tool_type_attr():
    return Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )[0]


def _option(attr, value, slug):
    return AttributeOption.objects.get_or_create(
        attribute=attr, value=value, defaults={"slug": slug}
    )[0]


@pytest.mark.django_db
def test_existing_web_pav_replaced_by_approved_manual_change(
    feature_enabled, reviewer, tool_type_attr
):
    """Контракт remediation ADR-0011 на существующем CatalogChange/apply-сервисе.

    Baseline: klyuchi-gaechnye/web/85 → approved manual change
    (dinamometricheskie-klyuchi, source=manual, confidence=100) → applied.
    Новых типов change/status не вводится.
    """
    attr = tool_type_attr
    old_option = _option(attr, "Ключи гаечные", "klyuchi-gaechnye")
    new_option = _option(attr, NEW_VALUE, NEW_SLUG)
    category = Category.add_root(
        name=f"Кат-{uuid.uuid4().hex[:8]}", slug=f"cat-{uuid.uuid4().hex[:8]}"
    )
    product = Product.objects.create(
        category=category,
        name="",
        slug="p-dinamometricheskiy",
        original_name='Ключ динамометрический 1/2" 28-210 Нм',
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="2500",
        description="do not touch",
    )
    # Существующий web PAV (как у 12957/12959): klyuchi-gaechnye/web/85.
    ProductAttributeValue.objects.create(
        product=product,
        attribute=attr,
        value_option=old_option,
        source=Source.WEB,
        confidence=85,
    )
    from apps.catalog.read_models import rebuild_attrs_cache

    rebuild_attrs_cache(product)

    run = CatalogProcessingRun.objects.create(
        kind="manual",
        mode="tool_type",
        status=CatalogProcessingRunStatus.RUNNING,
        idempotency_key=f"run-{uuid.uuid4()}",
    )
    snapshot = tool_type_snapshot(product)
    item = CatalogProcessingItem.objects.create(
        run=run,
        product=product,
        product_ref=product.pk,
        status=CatalogProcessingItemStatus.PENDING,
        input_snapshot=snapshot,
        input_hash=canonical_hash(snapshot),
        baseline_hashes={"tool_type": canonical_hash(processing._operational_baseline(snapshot))},
        needed_targets=["tool_type"],
    )

    cmd = processing.CatalogChangeCommand(
        item_id=item.pk,
        target_kind="tool_type",
        proposed_value={"option_slug": NEW_SLUG},
        source="manual",
        confidence=100,
        idempotency_key=str(uuid.uuid4()),
    )
    proposed = processing.create_catalog_change(cmd)
    assert proposed.status == "proposed"

    reviewed = processing.review_catalog_change(
        proposed.change_id, CatalogChangeStatus.APPROVED, reviewer.pk
    )
    assert reviewed.status == "approved"

    result = processing.apply_catalog_change(proposed.change_id, actor_id=reviewer.pk)

    assert result.status == "applied"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    # before_value сохраняет исходный web baseline.
    assert change.before_value["option_slug"] == "klyuchi-gaechnye"
    assert change.before_value["source"] == Source.WEB
    assert change.before_value["confidence"] == 85
    # after_value и audit заполнены.
    assert change.after_value["option_slug"] == NEW_SLUG
    assert change.after_value["source"] == "manual"
    assert change.after_value["confidence"] == 100
    assert change.reviewed_by_id == reviewer.pk
    assert change.reviewed_at is not None
    assert change.applied_by_id == reviewer.pk
    assert change.applied_at is not None

    # PAV: ровно один tool_type, заменён на новую option.
    pav = ProductAttributeValue.objects.get(product=product, attribute=attr)
    assert pav.value_option == new_option
    assert pav.source == "manual"
    assert pav.confidence == 100

    product.refresh_from_db()
    assert product.attrs_cache.get("tool_type") == NEW_VALUE
    # Посторонние поля не изменились.
    assert product.description == "do not touch"
    assert product.price == Decimal("2500.00")
    assert product.original_name == 'Ключ динамометрический 1/2" 28-210 Нм'

    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.COMPLETED
