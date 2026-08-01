"""Тесты canonical taxonomy manifest (Wave 7.1 / Stage H1, commit 1).

Покрывает: загрузку committed manifest, hash-контракты (identity permutation-
invariant и sort_order-индифферентен; semantic чувствителен к display/audit
полям), fail-closed валидацию (duplicates, empty, alias-инварианты, allow-list,
tampered hashes) и cross-validation legacy extraction rules против manifest.
"""

import json
from pathlib import Path

from django.conf import settings

from apps.catalog.rules_engine import load_ruleset, validate_against_taxonomy
from apps.catalog.taxonomy_manifest import (
    MANIFEST_PATH,
    load_manifest,
    load_options_index,
    manifest_semantic_hash,
    taxonomy_identity_hash,
    validate_manifest_doc,
)

V2_PATH = Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type.v2.json"
SEED_RULES_PATH = Path(settings.BASE_DIR) / "data" / "tool_type_rules.json"

# TT-NEW-TYPES-BATCH-2 (2026-08-01): пакет из 10 опций (phase8 taxonomy-gaps;
# 355 options; voronki не создан — дубликат hoz-voronki из TT-14) —
# identity и semantic hash пересчитаны;
# разметка gate-sample не переразмечалась (2 строки, как в TT-NEW-TYPES-BATCH/TT-14/TT-07/TT-01).
PINNED_IDENTITY_HASH = "8eba9631ad083d4d96e718c37c31726a8811e1562d5b1f6f12fa65c738cd1b9e"
# H4: clean-taxonomy снял 15 pending_business_review (identity_hash не менялся —
# slug/value не тронуты; semantic_hash покрывает origin/review metadata).
PINNED_SEMANTIC_HASH = "ed1b2a14caa0c128b00a19d0b8ce048865eb6da0603a9f9447009f2363add205"

BACKPORTED_SLUGS = {
    "bp-podgotovka-vozduha",
    "kobury-dlya-instrumenta",
    "sumki-poyasnye",
    "sterzhni-kleevye",
}
# Опции, созданные документированными раундами каталога; в H1 были помечены
# origin_kind=legacy_unknown из-за отсутствия в seed-файле, в H4 provenance
# восстановлен и они переведены в manual_backport/approved.
REBOUND_BACKPORT_SLUGS = {
    "stroitelnye-lesa-vyshki",
    "kovshi-shtukaturnye",
    "fiksatory-germetiki-rezby",
    "kukhonnye-razdelochnye-nozhi",
    "rukoyatki-dlya-instrumenta",
    "spetsialnye-nozhi",
    "aksessuary-dlya-klyuchey",
    "armiruyushchie-lenty-binty",
    "skruchevateli-provoloki",
    "bp-osnastka-pnevmomolotkov",
    "bp-nabory-pnevmoinstrumenta",
}
UNUSED_SLUGS = {"hoz-schetchiki", "osnastka-rezbonarez", "metchiki", "plashki"}
COLLISION_WINNERS = {
    "krep-zamki": "hoz-zamki",
    "pistolety-kleevye": "kleevye-pistolety",
    "izm-lupy": "hoz-lupy",
    "krep-provoloka": "hoz-provoloka",
    "hoz-steklorezy": "steklorezy",
    "obor-telezhki": "svar-telezhki",
    "bp-shlangi": "zap-shlangi",
}


def _doc(options, **overrides):
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
    return doc


def _opt(slug, value, **kw):
    base = {"slug": slug, "value": value}
    base.update(kw)
    return base


# --- committed manifest (canonical artifact pins) ---


def test_committed_manifest_loads_and_matches_pins():
    m = load_manifest()
    assert len(m.options) == 355
    assert m.identity_hash == PINNED_IDENTITY_HASH
    assert m.semantic_hash == PINNED_SEMANTIC_HASH
    assert m.schema_version == 1 and m.manifest_version == 1
    assert m.attribute_slug == "tool_type"


def test_all_default_v2_slugs_exist_in_manifest():
    manifest = load_manifest()
    ruleset = load_ruleset(V2_PATH)
    assert validate_against_taxonomy(ruleset, manifest.slugs) == []


def test_backported_slugs_present():
    m = load_manifest()
    assert BACKPORTED_SLUGS <= m.slugs


def test_no_pending_business_review_left():
    """H4: все 15 «серых» записей разобраны решением владельца."""
    m = load_manifest()
    assert {o.slug for o in m.options if o.review_status != "approved"} == set()
    assert {o.slug for o in m.options if o.origin_kind == "legacy_unknown"} == set()


def test_rebound_slugs_carry_origin_ref():
    """Записи, чей provenance восстановлен в H4, обязаны ссылаться на раунд."""
    m = load_manifest()
    by_slug = {o.slug: o for o in m.options}
    for slug in REBOUND_BACKPORT_SLUGS:
        opt = by_slug[slug]
        assert opt.origin_kind == "manual_backport", slug
        assert opt.origin_ref, slug
        assert opt.review_ref == "wave7-h4", slug


def test_unused_slugs_kept_with_written_decision():
    """4 неиспользуемые seed-опции оставлены осознанно, с зафиксированной причиной."""
    m = load_manifest()
    by_slug = {o.slug: o for o in m.options}
    for slug in UNUSED_SLUGS:
        opt = by_slug[slug]
        assert opt.origin_kind == "seed", slug
        assert opt.review_status == "approved", slug
        assert opt.review_ref == "wave7-h4", slug


def test_collision_winners_carry_losing_alias_and_approved():
    m = load_manifest()
    by_slug = {o.slug: o for o in m.options}
    for winner, loser in COLLISION_WINNERS.items():
        opt = by_slug[winner]
        assert opt.legacy_aliases == (loser,)
        assert opt.review_status == "approved"


def test_options_index_runtime_contract():
    idx = load_options_index()
    assert idx.by_slug("sterzhni-kleevye").value == "Клеевые стержни"
    assert idx.by_normalized_value("Клеевые стержни").slug == "sterzhni-kleevye"
    assert idx.by_slug("net-takogo-sluga") is None


# --- hash contracts ---


def test_identity_hash_permutation_invariant():
    a = [_opt("b-slug", "Б"), _opt("a-slug", "А"), _opt("c-slug", "В")]
    b = [a[2], a[0], a[1]]
    assert taxonomy_identity_hash(a) == taxonomy_identity_hash(b)


def test_identity_hash_ignores_sort_order_and_metadata():
    base = [_opt("a-slug", "А", sort_order=1), _opt("b-slug", "Б", sort_order=2)]
    reordered_meta = [
        _opt("a-slug", "А", sort_order=99, origin_kind="legacy_unknown"),
        _opt("b-slug", "Б", sort_order=0),
    ]
    assert taxonomy_identity_hash(base) == taxonomy_identity_hash(reordered_meta)


def test_semantic_hash_sensitive_to_sort_order():
    doc_a = _doc([_opt("a-slug", "А", sort_order=1)])
    doc_b = _doc([_opt("a-slug", "А", sort_order=2)])
    assert doc_a["manifest_semantic_hash"] != doc_b["manifest_semantic_hash"]


def test_identity_hash_changes_on_value_change():
    a = [_opt("a-slug", "А")]
    b = [_opt("a-slug", "Б")]
    assert taxonomy_identity_hash(a) != taxonomy_identity_hash(b)


# --- fail-closed validation ---


def test_validate_rejects_duplicate_slug():
    doc = _doc([_opt("a-slug", "А"), _opt("a-slug", "Б")])
    assert any("duplicate slug" in v for v in validate_manifest_doc(doc))


def test_validate_rejects_empty_slug_and_value():
    assert validate_manifest_doc(_doc([_opt("", "А")]))
    assert validate_manifest_doc(_doc([_opt("a-slug", "")]))
    assert validate_manifest_doc(_doc([_opt("a-slug", "  ")]))


def test_validate_rejects_bad_slug_pattern():
    assert validate_manifest_doc(_doc([_opt("Bad Slug", "А")]))
    assert validate_manifest_doc(_doc([_opt("-slug", "А")]))


def test_validate_rejects_alias_equal_own_slug():
    doc = _doc([_opt("a-slug", "А", legacy_aliases=["a-slug"])])
    assert any("собственным slug" in v for v in validate_manifest_doc(doc))


def test_validate_rejects_alias_equal_active_slug():
    doc = _doc(
        [
            _opt("a-slug", "А", legacy_aliases=["b-slug"]),
            _opt("b-slug", "Б"),
        ]
    )
    assert any("active slug" in v for v in validate_manifest_doc(doc))


def test_validate_rejects_duplicate_alias_within_option():
    doc = _doc([_opt("a-slug", "А", legacy_aliases=["old-one", "old-one"])])
    assert any("duplicate alias" in v for v in validate_manifest_doc(doc))


def test_validate_rejects_duplicate_semantic_value_outside_allowlist():
    doc = _doc([_opt("a-slug", "А"), _opt("b-slug", "А")])
    assert any("duplicate semantic value" in v for v in validate_manifest_doc(doc))


def test_validate_allows_duplicate_semantic_value_inside_allowlist():
    doc = _doc(
        [_opt("a-slug", "А"), _opt("b-slug", "А")],
        semantic_duplicate_allowlist=[["a-slug", "b-slug"]],
    )
    assert validate_manifest_doc(doc) == []


def test_validate_rejects_invalid_origin_and_review_status():
    assert validate_manifest_doc(_doc([_opt("a-slug", "А", origin_kind="mystery")]))
    assert validate_manifest_doc(_doc([_opt("a-slug", "А", review_status="maybe")]))


def test_validate_rejects_tampered_hashes():
    doc = _doc([_opt("a-slug", "А")])
    doc["taxonomy_identity_hash"] = "0" * 64
    assert any("taxonomy_identity_hash" in v for v in validate_manifest_doc(doc))
    doc = _doc([_opt("a-slug", "А")])
    doc["manifest_semantic_hash"] = "0" * 64
    assert any("manifest_semantic_hash" in v for v in validate_manifest_doc(doc))


def test_validate_rejects_nonlist_options_and_bad_versions():
    bad = _doc([_opt("a-slug", "А")])
    bad["options"] = {}
    assert validate_manifest_doc(bad)
    bad2 = _doc([_opt("a-slug", "А")], manifest_version=0)
    assert validate_manifest_doc(bad2)


# --- cross-validation: legacy extraction rules vs manifest ---


def test_extraction_rule_slugs_are_active_or_registered_alias():
    m = load_manifest()
    alias_pool = {alias for o in m.options for alias in o.legacy_aliases}
    seed_doc = json.loads(SEED_RULES_PATH.read_text(encoding="utf-8"))
    unclassified = []
    for cat in seed_doc["categories"]:
        for rule in cat.get("rules", []):
            if rule.get("action") == "recategorize":
                continue  # routing marker, не option-slug
            slug = rule["slug"]
            if slug not in m.slugs and slug not in alias_pool:
                unclassified.append(slug)
    assert unclassified == []


def test_manifest_file_is_canonically_ordered():
    doc = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    slugs = [o["slug"] for o in doc["options"]]
    assert slugs == sorted(slugs)
