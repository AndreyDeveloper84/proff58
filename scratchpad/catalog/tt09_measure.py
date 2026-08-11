"""TT-09 · замер: что предложил бы движок по всему каталогу (read-only).

Тот же matcher, что и catalog_rules_shadow (evaluate_product, candidate rules
текущего ruleset), но пул — ВСЕ eligible-товары (включая уже типизированные —
shadow их исключает, а для класса «расхождение» они и нужны). Записей в БД
нет: только чтение. Каталог под окном меняется чужими операциями (CAT-08/09
пишут на staging; локальная БД — предмет замера, момент зафиксирован).

Запуск: manage.py shell -c "exec(open('scratchpad/catalog/tt09_measure.py', encoding='utf-8').read())"
Выход: scratchpad/catalog/tt-09-measure.json
"""

from __future__ import annotations

import io
import json
import time

from django.db.models import Exists, OuterRef
from django.db.models.functions import Trim

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.rules_engine import TIER_CANDIDATE, ProductFacts, evaluate_product, load_ruleset

OUT = "scratchpad/catalog/tt-09-measure.json"

t0 = time.time()
ruleset = load_ruleset(None)
rules = [r for r in ruleset.rules if r.tier == TIER_CANDIDATE]
print("rules:", len(rules), "| ruleset_hash:", ruleset.ruleset_hash[:12])

# Вселенная = eligible-контракт контура (shadow, pool=all): активные,
# не content_locked, непустой article (Trim). Без stock-фильтра.
has_tt = ProductAttributeValue.objects.filter(
    product_id=OuterRef("pk"), attribute__slug="tool_type", value_option__isnull=False
)
universe = (
    Product.objects.annotate(_has_tt=Exists(has_tt), _art=Trim("article"))
    .filter(is_active=True, content_locked=False)
    .exclude(_art="")
    .order_by("pk")
)
total_products = Product.objects.count()
print("products всего:", total_products, "| universe eligible:", universe.count())

current = {}
for row in ProductAttributeValue.objects.filter(attribute__slug="tool_type").select_related("value_option"):
    current[row.product_id] = row.value_option.slug if row.value_option else None

rows = []
for p in universe.iterator(chunk_size=500):
    facts = ProductFacts(
        product_id=p.pk,
        name=p.name or "",
        original_name=p.original_name or "",
        brand=p.brand or "",
        source_group=p.source_group or "",
        article=p.article or "",
    )
    verdict = evaluate_product(rules, facts)
    cur = current.get(p.pk)
    proposed = verdict.option_slug if verdict.status == "prediction" else None
    collision = verdict.status == "collision"
    if cur is None and proposed:
        cls = "empty_to_proposal"
    elif cur is not None and proposed == cur:
        cls = "match"
    elif cur is not None and proposed and proposed != cur:
        cls = "mismatch"
    elif cur is not None and not proposed:
        cls = "silent_typed"
    else:
        cls = "silent_empty"
    rows.append({
        "pid": p.pk, "cur": cur, "proposed": proposed,
        "collision": collision, "cls": cls,
        "is_published": bool(p.is_active and p.status == "published"),
        "category_id": p.category_id,
    })

with io.open(OUT, "w", encoding="utf-8") as fh:
    json.dump({
        "meta": {
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ruleset_hash": ruleset.ruleset_hash,
            "rules_count": len(rules),
            "universe": "active, not content_locked, article non-empty (pool=all)",
            "total_products": total_products,
        },
        "rows": rows,
    }, fh, ensure_ascii=False)

from collections import Counter
c = Counter(r["cls"] for r in rows)
print("seconds:", round(time.time() - t0, 1))
print("classes:", dict(c))
print("written:", OUT)
