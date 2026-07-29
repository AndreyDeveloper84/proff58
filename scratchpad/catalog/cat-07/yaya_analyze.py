# -*- coding: utf-8 -*-
"""CAT-07 · задача 4: яя-префикс — цифры, сортировка, дубли. READ-ONLY."""
import io
import json
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db.models import Count  # noqa: E402

from apps.catalog.models import Product  # noqa: E402

out = {}

# 1. Цифры по префиксу (по обоим полям имени)
qs = Product.objects.filter(name__istartswith="яя")
out["name_ya"] = {"total": qs.count(), "pub": qs.filter(is_active=True, status="published").count()}
qs2 = Product.objects.filter(original_name__istartswith="яя")
out["original_ya"] = {
    "total": qs2.count(),
    "pub": qs2.filter(is_active=True, status="published").count(),
}
both = Product.objects.filter(name__istartswith="яя", original_name__istartswith="яя").count()
out["both_fields"] = both

# 2. Дубли после снятия префикса: stripped(name) совпадает с name другого товара
ya = list(qs.values_list("id", "name"))
stripped = {}
for pid, name in ya:
    s = name[2:].lstrip()
    stripped.setdefault(s.lower(), []).append(pid)
all_names = {}
for pid, name in Product.objects.values_list("id", "name"):
    all_names.setdefault(name.lower(), []).append(pid)
dup_with_other = 0
dup_inside_ya = 0
examples = []
for s, pids in stripped.items():
    other = [p for p in all_names.get(s, []) if p not in pids]
    if other:
        dup_with_other += len(pids)
        if len(examples) < 8:
            examples.append((s, pids, other))
    if len(pids) > 1:
        dup_inside_ya += len(pids)
out["dup_after_strip"] = {
    "collides_with_other_product": dup_with_other,
    "collides_inside_ya_set": dup_inside_ya,
    "examples": examples,
}

# 3. Где лежат яя-товары: топ категорий и первые слова после префикса
cats = Counter()
fw = Counter()
for p in qs.select_related("category"):
    cats[(p.category_id, p.category.name if p.category else None)] += 1
    w = p.name[2:].lstrip().lower().split(" ")[0].split(",")[0]
    fw[w] += 1
out["top_categories"] = [(str(k), v) for k, v in cats.most_common(10)]
out["top_first_word_after_strip"] = fw.most_common(15)

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
