"""TT-01 — добавление izm-areometry в canonical manifest + пересчёт hash-полей.

Dry-run по умолчанию; --apply пишет файл. Сериализация — та же, что у файла
(indent=2, ensure_ascii=False, LF, trailing newline) — git diff обязан быть
минимальным: новая опция + две hash-строки.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_SECRET_KEY", "tt01-local")

import django  # noqa: E402

django.setup()

from apps.catalog.taxonomy_manifest import (  # noqa: E402
    manifest_semantic_hash,
    taxonomy_identity_hash,
)

MANIFEST = ROOT / "data/catalog_processing_rules/tool_type_taxonomy.v1.json"

NEW_OPTION = {
    "slug": "izm-areometry",
    "value": "Ареометры (денсиметры)",
    "sort_order": 18,
    "origin_kind": "manual_backport",
    "origin_ref": "phase8 step2 recheck + owner decision 2026-07-28",
    "review_status": "approved",
    "review_reason": (
        "9 из 10 ареометров batch упираются в catch-all izm-analizatory — "
        "подходящего типа нет (перепроверка на всех 328 values, дельта ноль). "
        "Обоснование: §П6 scratchpad/phase8/phase8-step2-report.md"
    ),
    "review_ref": "phase8-step2-p6",
    "legacy_aliases": [],
}

APPLY = "--apply" in sys.argv


def main() -> int:
    raw = MANIFEST.read_bytes()
    assert b"\r\n" not in raw, "CRLF в исходнике — сериализация сломает диф"
    doc = json.loads(raw.decode("utf-8"))

    slugs = [o["slug"] for o in doc["options"]]
    assert "izm-areometry" not in slugs, "уже добавлен"
    assert slugs == sorted(slugs), "options не отсортированы по slug"
    assert not any(o["value"] == NEW_OPTION["value"] for o in doc["options"]), "value занято"

    # вставка в алфавитную позицию (после izm-analizatory)
    idx = next(i for i, s in enumerate(slugs) if s > NEW_OPTION["slug"])
    doc["options"].insert(idx, NEW_OPTION)

    doc["taxonomy_identity_hash"] = taxonomy_identity_hash(
        [{"slug": o["slug"], "value": o["value"]} for o in doc["options"]]
    )
    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)

    out = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    print("new identity_hash:", doc["taxonomy_identity_hash"])
    print("new semantic_hash:", doc["manifest_semantic_hash"])
    print("options:", len(doc["options"]), "inserted at index", idx)
    print("size delta:", len(out) - len(raw), "bytes")

    if APPLY:
        MANIFEST.write_bytes(out)
        print("ЗАПИСАНО.")
    else:
        print("DRY-RUN (передайте --apply).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
