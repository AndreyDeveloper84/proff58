"""Wave 7.1 / H1: генерация canonical taxonomy manifest (one-off generator, evidence).

Источники: staging dump (328 options) + seed (collision/provenance) + known manual rounds.
Записывает data/catalog_processing_rules/tool_type_taxonomy.v1.json.
Затем валидирует через apps.catalog.taxonomy_manifest и печатает hashes.
"""
import json
from collections import defaultdict

ROOT = "C:/Users/user/PycharmProjects/proff58"

staging = json.load(open(f"{ROOT}/scratchpad/wave7/staging-tool_type-usage.json", encoding="utf-8"))
seed_doc = json.load(open(f"{ROOT}/data/tool_type_rules.json", encoding="utf-8"))

seed_by_value = defaultdict(list)
for cat in seed_doc["categories"]:
    for r in cat.get("rules", []):
        if r.get("action") == "recategorize":
            continue
        seed_by_value[r["tool_type"]].append(r["slug"])

MANUAL = {
    428: "catalog-readiness-roadmap round 3",
    431: "catalog-readiness-roadmap round 4",
    432: "catalog-readiness-roadmap round 4",
    433: "catalog-readiness-roadmap round 5",
}
UNUSED_REVIEW = "unused by products and ruleset; removal — отдельное бизнес-решение"
LEGACY_REVIEW = "PAV-backed option без репозиторного provenance; каноничность подтверждена inventory Wave 7.1"
COLLISION_NOTE = "seed value collision: staging slug == current winner (verified 2026-07-23); loser — extraction-only legacy alias"

options = []
for o in staging:
    slug, value, oid, pav = o["slug"], o["value"], o["id"], o["pav_count"]
    seed_slugs = seed_by_value.get(value, [])
    origin_kind = "seed"
    origin_ref = None
    review_status = "approved"
    review_reason = ""
    review_ref = None
    legacy_aliases: list[str] = []
    if oid in MANUAL:
        origin_kind = "manual_backport"
        origin_ref = MANUAL[oid]
        review_reason = "v2-required backport (blocker A Wave 7)"
        review_ref = "wave7-inventory"
    elif not seed_slugs:
        origin_kind = "legacy_unknown"
        review_status = "pending_business_review"
        review_reason = LEGACY_REVIEW
        review_ref = "wave7-inventory"
    if len(set(seed_slugs)) > 1:
        losers = [s for s in seed_slugs if s != slug]
        legacy_aliases = losers
        if review_status == "approved":
            review_reason = COLLISION_NOTE
            review_ref = "wave7-inventory"
    if pav == 0:
        review_status = "pending_business_review"
        review_reason = UNUSED_REVIEW
        review_ref = "wave7-inventory"
    options.append(
        {
            "slug": slug,
            "value": value,
            "sort_order": o["sort_order"],
            "origin_kind": origin_kind,
            "origin_ref": origin_ref,
            "review_status": review_status,
            "review_reason": review_reason,
            "review_ref": review_ref,
            "legacy_aliases": legacy_aliases,
        }
    )

options.sort(key=lambda x: x["slug"])

doc = {
    "schema_version": 1,
    "manifest_version": 1,
    "attribute_slug": "tool_type",
    "status": "canonical",
    "provenance": {
        "basis": "staging live taxonomy (identity == pinned b357be60… legacy DB-order hash, verified 2026-07-23) + repository seed reconciliation (Wave 7.1)",
        "staging_dump": "AttributeOption queryset dump 2026-07-23 (328 options, ids 1..436)",
        "classification": "wave7 taxonomy inventory (328 rows): 313 in_seed, 15 non-seed (11 legacy_unknown PAV-backed, 4 manual_backport v2-required)",
        "notes": [
            "Все 328 options сохранены; удалений и переименований нет.",
            "7 seed value-collisions разрешены в staging winners; losers — extraction-only legacy aliases.",
            "Legacy _taxonomy_hash (DB-order, b357be60…) не смешивается с hashes этого manifest.",
        ],
    },
    "future_evolution": {
        "immutable_option_identity": {
            "status": "planned, not implemented",
            "summary": "В будущей версии manifest каждая option получит стабильный option_uid (например UUIDv5 от namespace + slug на момент введения), неизменный при переименовании value или reslug. Provenance (CatalogChange.evidence), release manifests и AI findings смогут ссылаться на option_uid вместо пары (slug, value).",
            "migration_path": [
                "manifest_version 2: добавление option_uid (additive; taxonomy_identity_hash не меняется — slug/value остаются runtime contract)",
                "consumers (provenance, release manifest, AI findings) начинают записывать option_uid рядом со slug",
                "позднее: option_uid становится primary reference для cross-release ссылок; slug остаётся operational key в БД",
            ],
            "out_of_scope_now": "генерация и хранение option_uid в H1 не реализуются",
        }
    },
    "semantic_duplicate_allowlist": [],
    "options": options,
}

import sys

sys.path.insert(0, ROOT)
from apps.catalog.taxonomy_manifest import (  # noqa: E402
    manifest_semantic_hash,
    taxonomy_identity_hash,
    validate_manifest_doc,
)

doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)

out = f"{ROOT}/data/catalog_processing_rules/tool_type_taxonomy.v1.json"
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
    f.write("\n")

# validation round-trip
reloaded = json.load(open(out, encoding="utf-8"))
violations = validate_manifest_doc(reloaded)
print("options:", len(doc["options"]))
print("identity:", doc["taxonomy_identity_hash"])
print("semantic:", doc["manifest_semantic_hash"])
print("violations:", violations or "none")
from collections import Counter

print("review_status:", Counter(o["review_status"] for o in options))
print("origin_kind:", Counter(o["origin_kind"] for o in options))
print("aliases:", {o["slug"]: o["legacy_aliases"] for o in options if o["legacy_aliases"]})
