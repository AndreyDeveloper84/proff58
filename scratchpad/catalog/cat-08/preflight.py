# -*- coding: utf-8 -*-
"""CAT-08 · задача 1: preflight яя — цифры, регистр, остаточные. READ-ONLY."""
import io
import json
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product  # noqa: E402

out = {}

# Базовые цифры
qs = Product.objects.filter(name__istartswith="яя")
out["istartswith_яя"] = qs.count()

# Варианты регистра (БД-регистронезависимость уже покрыта istartswith — считаем фактические)
variants = Counter()
for n in Product.objects.filter(name__iregex=r"^\s*я").values_list("name", flat=True):
    m = re.match(r"^\s*(я+)", n)
    if m:
        variants[m.group(1)] += 1
out["leading_ya_runs"] = dict(variants)

# яя НЕ в начале (такие не трогаем) — для протокола
mid = Product.objects.filter(name__icontains="яя").exclude(name__istartswith="яя")
out["я_внутри_не_в_начале"] = mid.count()
out["я_внутри_примеры"] = list(mid.values_list("id", "name")[:8])

# Полный разбор целевого множества по правилу оркестратора ^\s*яя\s*
residual = []
clean = []
for pid, name in qs.values_list("id", "name"):
    new = re.sub(r"^\s*яя\s*", "", name)
    if new and new[0].lower() == "я":
        residual.append((pid, name))
    else:
        clean.append((pid, name, new))
out["residual_25"] = residual
out["clean_count"] = len(clean)
out["empty_after"] = sum(1 for _, _, n in clean if not n.strip())

# Дубли: очищенное имя совпадёт с существующим товаром / внутри группы
new_names = {}
for pid, name, new in clean:
    new_names.setdefault(new.strip().lower(), []).append((pid, name))
all_names = {}
for pid, name in Product.objects.values_list("id", "name"):
    all_names.setdefault(name.strip().lower(), []).append(pid)
dup_other = []
dup_inside = []
for key, pids in new_names.items():
    others = [p for p in all_names.get(key, []) if p not in [x[0] for x in pids]]
    if others:
        for pid, old in pids:
            dup_other.append((pid, others[0], old))
    if len(pids) > 1:
        for i in range(1, len(pids)):
            dup_inside.append((pids[0][0], pids[i][0], pids[0][1]))
out["dup_other_59"] = dup_other
out["dup_inside_68"] = dup_inside

print(json.dumps(out, ensure_ascii=False, default=str))
