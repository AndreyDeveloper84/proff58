# -*- coding: utf-8 -*-
"""Проверка критериев приёмки Phase 2 (Task 5) по артефактам живого прогона."""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from parser.schemas import ErrorsExport, Export  # noqa: E402

OUT = Path("scratchpad/parser-mvp/output")
LOG = Path("scratchpad/parser-mvp/phase2-fetch-log.jsonl")

# --- критерий 1: валидный JSON, len(products) -------------------------------
total = 0
counts = {}
for source in ("resanta", "vihr", "interskol", "zubr"):
    export = Export.model_validate_json((OUT / f"{source}.products.json").read_text("utf-8"))
    errors = ErrorsExport.model_validate_json((OUT / f"{source}.errors.json").read_text("utf-8"))
    counts[source] = (len(export.products), len(errors.errors))
    total += len(export.products)
    print(f"[1] {source}: products={len(export.products)} errors={len(errors.errors)} "
          f"category={export.category.name!r} url={export.category.source_url}")
print(f"[1] ИТОГО карточек: {total} (порог >= 20: {'OK' if total >= 20 else 'FAIL'})")

# --- критерий 3: журнал доступа ----------------------------------------------
records = [json.loads(line) for line in LOG.read_text("utf-8").splitlines()]
by_host = defaultdict(list)
for rec in records:
    host = rec["url"].split("/")[2].lower().removeprefix("www.")
    by_host[host].append(rec)
print(f"[3] строк журнала: {len(records)}")
bad = 0
for host, recs in sorted(by_host.items()):
    statuses = defaultdict(int)
    for r in recs:
        statuses[str(r["status"])] += 1
        if r["status"] in (401, 403, 429):
            bad += 1
    hits = sum(1 for r in recs if r["cache_hit"])
    real = [r for r in recs if not r["cache_hit"] and r.get("error") is None]
    ts = sorted(datetime.fromisoformat(r["ts"]) for r in real)
    deltas = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    min_delta = min(deltas) if deltas else None
    waits = [r["throttle_wait_s"] for r in real]
    print(f"[3] {host}: запросов {len(recs)} (сетевых {len(real)}, cache_hit {hits}), "
          f"статусы {dict(statuses)}, мин. интервал по ts "
          f"{f'{min_delta:.0f} с' if min_delta is not None else '—'}, "
          f"суммарный throttle_wait {sum(waits):.1f} с")
print(f"[3] ответов 401/403/429: {bad} ({'OK' if bad == 0 else 'FAIL'})")

# --- критерий 5: атомарность --------------------------------------------------
tmps = list(OUT.glob("*.tmp"))
print(f"[5] .tmp-файлов в output: {len(tmps)} ({'OK' if not tmps else 'FAIL'})")

# --- критерий 7: сырые значения с подписями -----------------------------------
needles = ("0-1100", "220-230", "230/50")
print("[7] примеры сырых значений:")
found = 0
for source in ("resanta", "vihr", "interskol", "zubr"):
    export = Export.model_validate_json((OUT / f"{source}.products.json").read_text("utf-8"))
    for card in export.products:
        for key, val in card.attributes.items():
            if found >= 6:
                break
            if any(n in val for n in needles):
                print(f"    {source} | {card.name[:45]} | {key} = {val!r}")
                found += 1

# --- критерий 8: дедуп Интерскола ---------------------------------------------
export = Export.model_validate_json((OUT / "interskol.products.json").read_text("utf-8"))
seen = {}
dupes = []
for card in export.products:
    key = (card.name.lower(), (card.manufacturer_sku or "").lower())
    if key in seen:
        dupes.append((seen[key], card.source_url))
    seen[key] = card.source_url
print(f"[8] интерскол: карточек {len(export.products)}, дублей (name, sku) "
      f"с разными URL: {len(dupes)} ({'OK' if not dupes else 'FAIL'})")
for a, b in dupes:
    print(f"    DUP: {a} == {b}")
