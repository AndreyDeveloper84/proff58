"""Wave 7.1 / H4.8 — clean-taxonomy: снятие 15 pending_business_review.

Решения владельца (2026-07-27):
  * 11 записей legacy_unknown -> approved + origin_kind=manual_backport +
    origin_ref на конкретный раунд каталога (provenance восстановлен обратным
    поиском по docs/, все имеют AttributeOption.id 418-429 и товары на staging);
  * 4 неиспользуемые seed-опции -> approved, остаются как пробел ассортимента.

Слияний и сплитов нет. slug и value НЕ меняются, поэтому
taxonomy_identity_hash остаётся прежним; меняется только
manifest_semantic_hash (он покрывает origin/review metadata).

Запуск: uv run python -X utf8 scratchpad/wave7/h4_clean_taxonomy.py [--apply]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_SECRET_KEY", "h4-local")

import django  # noqa: E402

django.setup()

from apps.catalog.taxonomy_manifest import (  # noqa: E402
    MANIFEST_PATH,
    load_manifest,
    manifest_semantic_hash,
    taxonomy_identity_hash,
    validate_manifest_doc,
)

APPLY = "--apply" in sys.argv

# slug -> origin_ref раунда, в котором опция была СОЗДАНА
BACKPORT_ORIGIN = {
    "stroitelnye-lesa-vyshki": "stroitelnyy-roadmap round 1",
    "kovshi-shtukaturnye": "stroitelnyy-roadmap round 4",
    "fiksatory-germetiki-rezby": "stroitelnyy-roadmap round 4",
    "kukhonnye-razdelochnye-nozhi": "ruchnoy-roadmap round 11",
    "rukoyatki-dlya-instrumenta": "ruchnoy-roadmap round 12",
    "spetsialnye-nozhi": "ruchnoy-roadmap round 14",
    "aksessuary-dlya-klyuchey": "ruchnoy-roadmap round 15",
    "armiruyushchie-lenty-binty": "catalog-readiness-roadmap round 2",
    "skruchevateli-provoloki": "catalog-readiness-roadmap round 2",
    "bp-osnastka-pnevmomolotkov": "catalog-readiness-roadmap round 3",
    "bp-nabory-pnevmoinstrumenta": "catalog-readiness-roadmap round 3",
}
BACKPORT_REASON = (
    "provenance восстановлен в Wave 7.1 H4 обратным поиском по docs/: "
    "опция создана документированным раундом каталога и подтверждена товарами"
)

UNUSED_KEEP = ("hoz-schetchiki", "metchiki", "osnastka-rezbonarez", "plashki")
UNUSED_REASON = (
    "не используется товарами и ruleset; решением владельца (Wave 7.1 H4) "
    "оставлена как пробел ассортимента, удаление отложено до процедур отката H5"
)
REVIEW_REF = "wave7-h4"


def serialize(doc: dict) -> bytes:
    return json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def main() -> int:
    raw = MANIFEST_PATH.read_bytes()
    doc = json.loads(raw.decode("utf-8"))

    # --- 0. round-trip: сериализация обязана воспроизводить файл байт-в-байт ---
    if serialize(doc) != raw:
        print("СТОП: сериализация не воспроизводит текущий файл байт-в-байт.")
        print(f"  текущий={len(raw)} байт, пересериализованный={len(serialize(doc))} байт")
        return 2
    print("[0] round-trip сериализации байт-в-байт: OK")

    before_identity = doc["taxonomy_identity_hash"]
    before_semantic = doc["manifest_semantic_hash"]
    before_pairs = {o["slug"]: o["value"] for o in doc["options"]}

    changed = []
    for o in doc["options"]:
        slug = o["slug"]
        if slug in BACKPORT_ORIGIN:
            assert o["review_status"] == "pending_business_review", slug
            assert o["origin_kind"] == "legacy_unknown", slug
            o["origin_kind"] = "manual_backport"
            o["origin_ref"] = BACKPORT_ORIGIN[slug]
            o["review_status"] = "approved"
            o["review_reason"] = BACKPORT_REASON
            o["review_ref"] = REVIEW_REF
            changed.append(slug)
        elif slug in UNUSED_KEEP:
            assert o["review_status"] == "pending_business_review", slug
            assert o["origin_kind"] == "seed", slug
            o["review_status"] = "approved"
            o["review_reason"] = UNUSED_REASON
            o["review_ref"] = REVIEW_REF
            changed.append(slug)

    print(f"[1] изменено записей: {len(changed)} (ожидалось 15)")

    # --- инварианты ---
    after_pairs = {o["slug"]: o["value"] for o in doc["options"]}
    print(f"[2] множество slug/value не изменилось = {before_pairs == after_pairs}")
    print(f"[3] число options = {len(doc['options'])} (ожидалось 328)")

    new_identity = taxonomy_identity_hash(doc["options"])
    print(f"[4] taxonomy_identity_hash не изменился = {new_identity == before_identity}")
    print(f"    {new_identity}")

    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
    print("[5] manifest_semantic_hash:")
    print(f"    было  {before_semantic}")
    print(f"    стало {doc['manifest_semantic_hash']}")

    pend = [o for o in doc["options"] if o["review_status"] != "approved"]
    print(f"[6] pending_business_review осталось = {len(pend)} (ожидалось 0)")

    kinds = {}
    for o in doc["options"]:
        kinds[o["origin_kind"]] = kinds.get(o["origin_kind"], 0) + 1
    print(f"[7] origin_kind: {kinds}")

    violations = validate_manifest_doc(doc)
    print(f"[8] validate_manifest_doc: {violations or 'нарушений нет'}")
    if violations or new_identity != before_identity or before_pairs != after_pairs or pend:
        print("СТОП: инварианты нарушены, запись не выполняется.")
        return 2

    if APPLY:
        MANIFEST_PATH.write_bytes(serialize(doc))
        reloaded = load_manifest()
        print(f"\nЗАПИСАНО. Перечитан: options={len(reloaded.options)} "
              f"identity={reloaded.identity_hash} semantic={reloaded.semantic_hash}")
    else:
        print("\nDRY-RUN: файл не изменён (передайте --apply).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
