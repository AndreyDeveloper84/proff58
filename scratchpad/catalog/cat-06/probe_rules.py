# -*- coding: utf-8 -*-
"""CAT-06: проба драфта правил на полных списках названий (извлечение без БД-записи).

Локально: python probe_rules.py
Вывод: по каждому типу — все извлечённые значения с названиями (для глазной сверки),
число без значения, сводка покрытия.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from apps.catalog.attribute_extract import AttributeRules  # noqa: E402

base = Path(__file__).resolve().parent


def load_loose(path):
    raw = open(path, encoding="utf-8").read()
    return json.loads(raw[raw.index("{"):])


names = load_loose(base / "t2_names.json")
draft = load_loose(base / "rules_draft.json")
rules = AttributeRules.from_dict(draft)

report = {}
for tt, rows in names.items():
    got, missed = [], []
    for r in rows:
        vals = rules.extract(tt, r["name"])
        if vals:
            v = vals[0]
            got.append((r["pid"], r["pub"], str(v.number), v.matched, r["name"]))
        else:
            missed.append((r["pid"], r["pub"], r["name"]))
    pub_got = sum(1 for g in got if g[1])
    pub_total = sum(1 for r in rows if r["pub"])
    report[tt] = {
        "total": len(rows),
        "extracted": len(got),
        "pub_total": pub_total,
        "pub_extracted": pub_got,
        "pub_coverage": round(100.0 * pub_got / max(pub_total, 1), 1),
        "distinct": sorted({g[2] for g in got}),
        "got": got,
        "missed": missed,
    }

json.dump(report, open(base / "probe_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for tt, r in report.items():
    print(f"== {tt}: извлечено {r['extracted']}/{r['total']}, pub {r['pub_extracted']}/{r['pub_total']} ({r['pub_coverage']}%)")
    print("   distinct:", ", ".join(r["distinct"]))
