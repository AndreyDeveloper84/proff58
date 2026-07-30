#!/usr/bin/env python3
"""Сверка attribute_rules.json со staging-планом (plan_staging.json).

Пример:
    python scratchpad/catalog/scoped_rules_verify.py \
        --rules scratchpad/catalog/cat-06/scoped/attribute_rules.json \
        --plan scratchpad/catalog/cat-06/plan_staging.json

Exit code 0 только при полном совпадении всех значений.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import django


def setup_django():
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Сверка правил со staging-планом")
    parser.add_argument("--rules", required=True, help="Путь к attribute_rules.json")
    parser.add_argument("--plan", required=True, help="Путь к plan_staging.json")
    args = parser.parse_args()

    setup_django()
    from apps.catalog.attribute_extract import AttributeRules

    rules = AttributeRules.from_file(args.rules)

    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    expected_total = plan.get("summary", {}).get("CREATE", 0)
    creates = plan.get("plan", {}).get("create", [])

    matched = 0
    mismatched = 0
    missing = 0
    mismatches = []
    by_attr_tt = {}

    for rec in creates:
        tt = rec["tt"]
        attr = rec["attr"]
        expected = Decimal(str(rec["val"]))
        name = rec["name"]
        key = f"{attr}|{tt}"

        values = rules.extract(tt, name)
        found = {v.slug: v for v in values}
        value = found.get(attr)

        by_attr_tt[key] = by_attr_tt.get(key, {"total": 0, "matched": 0})
        by_attr_tt[key]["total"] += 1

        if value is None:
            missing += 1
            mismatches.append({"rec": rec, "reason": "missing"})
            continue

        actual = value.number
        if actual is None:
            mismatched += 1
            mismatches.append({"rec": rec, "reason": "not_number", "actual": str(value)})
            continue

        if actual == expected:
            matched += 1
            by_attr_tt[key]["matched"] += 1
        else:
            mismatched += 1
            mismatches.append({"rec": rec, "reason": "mismatch", "actual": str(actual)})

    print(f"Всего записей в плане: {len(creates)} (ожидалось CREATE={expected_total})")
    print(f"Совпало: {matched}")
    print(f"Не совпало: {mismatched}")
    print(f"Не извлечено: {missing}")
    print("\nПо attr|tt:")
    for key, stat in sorted(by_attr_tt.items()):
        print(f"  {key}: {stat['matched']}/{stat['total']}")

    if mismatches:
        print("\nПервые расхождения:")
        for m in mismatches[:10]:
            rec = m["rec"]
            print(f"  {m['reason']}: {rec['tt']}/{rec['attr']} val={rec['val']} name={rec['name']!r}")
            if "actual" in m:
                print(f"    actual={m['actual']}")

    return 0 if (matched == len(creates) and mismatched == 0 and missing == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
