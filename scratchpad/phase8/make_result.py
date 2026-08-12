"""Phase 8 · ступень 1 — «обработка» batch по контракту скилла catalog-research.

Скилл `catalog-research` выполняет web research. Товары этой ступени —
ФИКТИВНЫЕ (`PH8-SYN-*`), их не существует в природе, поэтому реальный web
research по ним невозможен и был бы фальсификацией evidence (прямой запрет
скилла: «выдуманные URL/evidence»).

Поэтому здесь воспроизводится ровно то, что скилл обязан сделать ПОСЛЕ
research, — детерминированная сборка result-файла по контракту:
- `export_checksum` берётся из поля `checksum` export-файла;
- `taxonomy_hash` и `input_hash` переносятся из export;
- option_slug выбирается ТОЛЬКО из `allowed_options`;
- evidence помечен доменом `synthetic.invalid` (RFC 2606, нерезолвимый) —
  никакой возможности выдать synthetic-прогон за реальный research.

Пять case-ов покрывают весь item-контракт:
  1  matched  / researched     / 1 change (высокая уверенность)
  2  matched  / researched     / 1 change (средняя уверенность)
  3  unknown  / unknown        / без changes
  4  partial  / review         / без changes
  5  mismatch / identity_failed/ без changes

Usage: uv run python scratchpad/phase8/make_result.py <run_id> [--variant NAME]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
OUTBOX = BASE / "var" / "catalog-processing" / "outbox"
INBOX = BASE / "var" / "catalog-processing" / "inbox"

RETRIEVED_AT = "2026-07-27T09:00:00Z"


def evidence(num: str, value: str) -> dict:
    return {
        "source_type": "manufacturer",
        "url": f"https://synthetic.invalid/phase8/ph8-syn-{num}",
        "title": f"SYNTHETIC PH8-SYN-{num} spec sheet (фиктивный источник)",
        "observed_value": value,
        "retrieved_at": RETRIEVED_AT,
    }


def build(run_id: str) -> dict:
    export = json.loads((OUTBOX / f"{run_id}.json").read_text(encoding="utf-8"))
    by_ref = {item["product_ref"]: item for item in export["items"]}
    allowed = {option["slug"] for option in export["allowed_options"]}
    for slug in ("perforatory", "dreli-shurupoverty"):
        if slug not in allowed:
            raise SystemExit(f"slug {slug} отсутствует в allowed_options")

    refs = sorted(by_ref)
    if len(refs) != 5:
        raise SystemExit(f"ожидалось 5 items, получено {len(refs)}")
    r1, r2, r3, r4, r5 = refs

    items = [
        {
            "product_ref": r1,
            "input_hash": by_ref[r1]["input_hash"],
            "identity": {
                "status": "matched",
                "brand": "SYNTHBRAND-A",
                "model": "PH8-SYN-001",
                "article": "PH8-SYN-ART-001",
                "reason": "synthetic exact article match",
            },
            "status": "researched",
            "reason_code": "synthetic_exact_match",
            "reason_detail": "CASE-1: фиктивный товар, точное совпадение артикула.",
            "changes": [
                {
                    "target_kind": "tool_type",
                    "proposed_value": {"option_slug": "perforatory"},
                    "confidence": 90,
                    "reason_code": "synthetic_model_match",
                    "reason_detail": "CASE-1: макет перфоратора.",
                    "source": "web",
                    "evidence": [evidence("001", "Перфоратор")],
                }
            ],
        },
        {
            "product_ref": r2,
            "input_hash": by_ref[r2]["input_hash"],
            "identity": {
                "status": "matched",
                "brand": "SYNTHBRAND-A",
                "model": "PH8-SYN-002",
                "article": "PH8-SYN-ART-002",
                "reason": "synthetic exact article match",
            },
            "status": "researched",
            "reason_code": "synthetic_exact_match",
            "reason_detail": "CASE-2: фиктивный товар, точное совпадение артикула.",
            "changes": [
                {
                    "target_kind": "tool_type",
                    "proposed_value": {"option_slug": "dreli-shurupoverty"},
                    "confidence": 75,
                    "reason_code": "synthetic_model_match",
                    "reason_detail": "CASE-2: макет шуруповёрта.",
                    "source": "web",
                    "evidence": [evidence("002", "Дрель-шуруповёрт")],
                }
            ],
        },
        {
            "product_ref": r3,
            "input_hash": by_ref[r3]["input_hash"],
            "identity": {"status": "unknown", "reason": "synthetic: источников нет"},
            "status": "unknown",
            "reason_code": "no_sources",
            "reason_detail": "CASE-3: идентичность не установлена, предложений нет.",
        },
        {
            "product_ref": r4,
            "input_hash": by_ref[r4]["input_hash"],
            "identity": {
                "status": "partial",
                "brand": "SYNTHBRAND-B",
                "reason": "synthetic: бренд найден, модель нет",
            },
            "status": "review",
            "reason_code": "ambiguous_target",
            "reason_detail": "CASE-4: тип спорный, требуется ручная модерация.",
        },
        {
            "product_ref": r5,
            "input_hash": by_ref[r5]["input_hash"],
            "identity": {
                "status": "mismatch",
                "brand": "SYNTHBRAND-C",
                "reason": "synthetic: найден другой товар",
            },
            "status": "identity_failed",
            "reason_code": "identity_mismatch",
            "reason_detail": "CASE-5: идентичность не подтверждена.",
        },
    ]

    return {
        "schema_version": "1.0",
        "run_id": export["run_id"],
        "taxonomy_hash": export["taxonomy_hash"],
        "export_checksum": export["checksum"],
        "items": items,
    }


def main() -> None:
    run_id = sys.argv[1]
    variant = ""
    if len(sys.argv) > 3 and sys.argv[2] == "--variant":
        variant = "." + sys.argv[3]
    data = build(run_id)
    INBOX.mkdir(parents=True, exist_ok=True)
    out = INBOX / f"{run_id}{variant}.result.json"
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(out)


if __name__ == "__main__":
    main()
