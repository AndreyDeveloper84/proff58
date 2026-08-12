# -*- coding: utf-8 -*-
"""CAT-08 · задача 2: dry-run — предсказание, rollback-map, примеры, дубли. READ-ONLY.

Критерий (дословно):
  1. Цель: name ~* '^\\s*яя' (регистронезависимо).
  2. new = re.sub(r'^\\s*я+\\s*', '', name, flags=IGNORECASE) — полный лидирующий ряд «я».
  3. Мусор (не трогаем): остаток пуст / без букв / короче 2 символов.
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product  # noqa: E402

RULE = re.compile(r"^\s*я+\s*", re.IGNORECASE)

plan = []   # (pid, old, new)
garbage = []  # (pid, old, reason)
for pid, name in Product.objects.filter(name__iregex=r"^\s*яя").values_list("id", "name"):
    new = RULE.sub("", name, count=1)
    rest = new.strip()
    if len(rest) < 2 or not re.search(r"[a-zа-яё]", rest, re.IGNORECASE):
        garbage.append((pid, name, "нет содержания после снятия" if rest else "пусто после снятия"))
    else:
        plan.append((pid, name, new))

# Дубли по новым именам
new_names = {}
for pid, old, new in plan:
    new_names.setdefault(new.strip().lower(), []).append((pid, old))
all_names = {}
for pid, name in Product.objects.values_list("id", "name"):
    all_names.setdefault(name.strip().lower(), []).append(pid)

dup_pairs = []
for key, pids in new_names.items():
    others = [p for p in all_names.get(key, []) if p not in [x[0] for x in pids]]
    for pid, old in pids:
        for o in others:
            dup_pairs.append({"type": "с_другим_товаром", "id_a": pid, "id_b": o, "name": pids[0][1] and key})
    if len(pids) > 1:
        base = pids[0]
        for other in pids[1:]:
            dup_pairs.append({"type": "внутри_яя", "id_a": base[0], "id_b": other[0], "name": key})

chars_saved = sum(len(o) - len(n) for _, o, n in plan)
out = {
    "target_total": len(plan) + len(garbage),
    "will_change": len(plan),
    "garbage": garbage,
    "chars_saved": chars_saved,
    "dup_pairs": dup_pairs,
    "dup_other": sum(1 for d in dup_pairs if d["type"] == "с_другим_товаром"),
    "dup_inside": sum(1 for d in dup_pairs if d["type"] == "внутри_яя"),
}
OUT = os.environ.get("CAT08_OUT", "/tmp/cat08_plan.json")
io.open(OUT, "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, default=str)
)
# rollback-map отдельным файлом
io.open(os.environ.get("CAT08_MAP", "/tmp/cat08_rollback_map.json"), "w", encoding="utf-8").write(
    json.dumps(
        [{"pid": pid, "old": old, "new": new} for pid, old, new in plan],
        ensure_ascii=False,
    )
)
print("WROTE", OUT, "| change:", len(plan), "| garbage:", len(garbage),
      "| chars:", chars_saved, "| dup:", out["dup_other"], "+", out["dup_inside"])
