"""TT-01 — перепривязка gate-sample на новый taxonomy binding (izm-areometry).

Смена binding, НЕ переразметка — точь-в-точь процедура H4
(scratchpad/wave7/h4_rebind_sample.py):
  1) точечная байтовая замена taxonomy_hash в sample: fc13be78… -> 524d4e31…;
  2) пересчёт canonical_hash(sample) и точечная замена labels.sample_hash;
  3) доказательства: изменилось РОВНО два поля, product_id/строки/ground truth
     не изменились, rows=103 correct=102 unverifiable=1.

Запуск: python -X utf8 scratchpad/catalog/tt01_rebind_sample.py [--apply]
Без --apply — dry-run (файлы не трогаются).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_SECRET_KEY", "tt01-local")

import django  # noqa: E402

django.setup()

from apps.catalog.processing import canonical_hash  # noqa: E402
from apps.catalog.taxonomy_manifest import load_manifest  # noqa: E402

FIX = Path("apps/catalog/tests/fixtures")
SAMPLE = FIX / "phase7d-gate-sample-official.json"
LABELS = FIX / "phase7d-labels.json"

OLD = "fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8"

APPLY = "--apply" in sys.argv


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ground_truth(labels: dict) -> dict:
    return {
        lb["product_id"]: {k: v for k, v in lb.items() if k != "product_id"}
        for lb in labels["labels"]
    }


def main() -> int:
    canonical = load_manifest().identity_hash
    print(f"new canonical taxonomy_identity_hash = {canonical}")
    print(f"old taxonomy_hash                    = {OLD}")
    assert canonical != OLD

    sample_before_bytes = SAMPLE.read_bytes()
    labels_before_bytes = LABELS.read_bytes()
    sample_before = json.loads(sample_before_bytes.decode("utf-8"))
    labels_before = json.loads(labels_before_bytes.decode("utf-8"))

    print("\n--- ДО ---")
    print(f"sample.taxonomy_hash = {sample_before['taxonomy_hash']}")
    print(f"labels.sample_hash   = {labels_before['sample_hash']}")
    print(f"canonical_hash(sample) пересчитанный = {canonical_hash(sample_before)}")

    occurrences = sample_before_bytes.count(OLD.encode())
    assert occurrences == 1, f"ожидалось ровно 1 вхождение старого хэша, найдено {occurrences}"
    assert sample_before["taxonomy_hash"] == OLD, "sample.taxonomy_hash != old"
    sample_after_bytes = sample_before_bytes.replace(OLD.encode(), canonical.encode())
    sample_after = json.loads(sample_after_bytes.decode("utf-8"))

    new_sample_hash = canonical_hash(sample_after)
    old_sample_hash = labels_before["sample_hash"]
    assert old_sample_hash == canonical_hash(sample_before), "labels не привязаны к текущему sample"
    occ_l = labels_before_bytes.count(old_sample_hash.encode())
    assert occ_l == 1, f"ожидалось ровно 1 вхождение sample_hash в labels, найдено {occ_l}"
    labels_after_bytes = labels_before_bytes.replace(
        old_sample_hash.encode(), new_sample_hash.encode()
    )
    labels_after = json.loads(labels_after_bytes.decode("utf-8"))

    print("\n--- ДОКАЗАТЕЛЬСТВО: смена binding, не переразметка ---")
    ids_before = [r["product_id"] for r in sample_before["rows"]]
    ids_after = [r["product_id"] for r in sample_after["rows"]]
    print(
        f"[1] product_id sample: порядок идентичен = {ids_before == ids_after}; "
        f"множество идентично = {set(ids_before) == set(ids_after)}; n={len(ids_after)}"
    )
    print(f"[2] строки sample идентичны = {sample_before['rows'] == sample_after['rows']}")
    diff_top = {
        k
        for k in set(sample_before) | set(sample_after)
        if sample_before.get(k) != sample_after.get(k)
    }
    print(f"[3] изменённые top-level поля sample = {sorted(diff_top)} (ожидалось: taxonomy_hash)")
    gt_before, gt_after = ground_truth(labels_before), ground_truth(labels_after)
    print(
        f"[4] ground truth идентичен = {gt_before == gt_after}; "
        f"labels product_id множество идентично = {set(gt_before) == set(gt_after)}"
    )
    diff_lt = {
        k
        for k in set(labels_before) | set(labels_after)
        if k != "labels" and labels_before.get(k) != labels_after.get(k)
    }
    print(f"[5] изменённые top-level поля labels = {sorted(diff_lt)} (ожидалось: sample_hash)")
    dec_b = Counter(lb["decision"] for lb in labels_before["labels"])
    dec_a = Counter(lb["decision"] for lb in labels_after["labels"])
    n = len(sample_after["rows"])
    print(
        f"[6] rows={n} correct={dec_a['correct']} unverifiable={dec_a['unverifiable']} "
        f"(ожидалось 103/102/1) -> "
        f"{n == 103 and dec_a['correct'] == 102 and dec_a['unverifiable'] == 1 and dec_b == dec_a}"
    )
    print(
        f"[7] покрытие: каждая строка sample имеет ровно один label = "
        f"{set(ids_after) == set(gt_after) and len(labels_after['labels']) == n}"
    )
    print(
        f"[8] ruleset_hash sample/labels без изменений = "
        f"{sample_before['ruleset_hash'] == sample_after['ruleset_hash']} / "
        f"{labels_before['ruleset_hash'] == labels_after['ruleset_hash']}; "
        f"matcher_version без изменений = "
        f"{sample_before['matcher_version'] == sample_after['matcher_version']}"
    )
    reviewer_keys = ["reviewer_id", "reviewed_at", "rationale"]
    print(
        f"[9] reviewer_id/reviewed_at/rationale идентичны = "
        + str(
            all(
                [lb[k] for lb in labels_before["labels"]]
                == [lb[k] for lb in labels_after["labels"]]
                for k in reviewer_keys
            )
        )
    )

    print("\n--- ПОСЛЕ ---")
    print(f"sample.taxonomy_hash = {sample_after['taxonomy_hash']}")
    print(f"labels.sample_hash   = {new_sample_hash}")
    crlf = b"\r\n"
    print(f"CRLF: sample={crlf in sample_after_bytes}, labels={crlf in labels_after_bytes}")
    print(
        f"дельта размера: sample={len(sample_after_bytes) - len(sample_before_bytes)}, "
        f"labels={len(labels_after_bytes) - len(labels_before_bytes)} (ожидалось 0/0)"
    )

    if APPLY:
        SAMPLE.write_bytes(sample_after_bytes)
        LABELS.write_bytes(labels_after_bytes)
        print("\nЗАПИСАНО (--apply).")
    else:
        print("\nDRY-RUN: файлы не изменены (передайте --apply).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
