"""TT-09 · read-only реплика enrich_attributes по крупным tool_type (задача 4).

У команды нет флага --dry-run — она всегда пишет (ImportRun + bulk PAV).
Поэтому считаем тем же движком (AttributeRules из data/attribute_rules.json),
не записывая: для товаров нескольких крупных tool_type — сколько значений
движок извлёк бы в ПУСТЫЕ поля (would_create), сколько переписал бы у
существующих с приоритетом ≤ нового (would_update), сколько заблокировано
приоритетом (skipped_priority).

Запуск: manage.py shell -c "exec(open('scratchpad/catalog/tt09_enrich_replica.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.models import Product, ProductAttributeValue

TOOL_TYPES = ["perforatory", "dreli-shurupoverty", "bolgarki-ushm", "shlifmashiny", "sverla"]

raw = json.loads(Path("data/attribute_rules.json").read_text(encoding="utf-8"))
rules = AttributeRules.from_dict(raw)
priority = rules.source_priority

managed_by_tt = {
    tt["tool_type"]: {a["slug"] for a in tt["attributes"]}
    for tt in raw.get("tool_types", [])
}

product_tt = {
    row["product_id"]: row["value_option__slug"]
    for row in ProductAttributeValue.objects.filter(
        attribute__slug="tool_type",
        value_option__isnull=False,
        value_option__slug__in=TOOL_TYPES,
    ).values("product_id", "value_option__slug")
}
print("товаров целевых типов:", len(product_tt))

managed_slugs = {s for slugs in managed_by_tt.values() for s in slugs}
existing = {}
for pav in ProductAttributeValue.objects.filter(
    product_id__in=product_tt, attribute__slug__in=managed_slugs
).select_related("attribute"):
    existing[(pav.product_id, pav.attribute.slug)] = pav

would_create = 0
would_update = 0
skipped_priority = 0
by_tt_create = Counter()
no_value_pav = 0
for p in Product.objects.filter(pk__in=product_tt).order_by("pk").iterator(chunk_size=500):
    tt = product_tt[p.pk]
    if not managed_by_tt.get(tt):
        continue
    for v in rules.extract(tt, p.name or ""):
        cur = existing.get((p.pk, v.slug))
        if cur is None:
            would_create += 1
            by_tt_create[tt] += 1
            continue
        cur_pr = priority.get(cur.source, 0)
        if v.priority >= cur_pr:
            would_update += 1
        else:
            skipped_priority += 1

print("would_create (в пустые поля):", would_create)
print("would_update (перезапись, priority нового >= текущего):", would_update)
print("skipped_priority (manual/1C не затираются):", skipped_priority)
print("by_tt create:", dict(by_tt_create))
