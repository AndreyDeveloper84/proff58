"""TT-06 · apply 11 одобренных findings run 00638eaa — одной транзакцией.

G1-эквивалент: run_id задан явно и перепроверен по каждому change
(change.item.run_id == RUN_ID); применяются ТОЛЬКО approved changes этого
run; количество должно быть ровно 11, иначе — отказ до записи.
Каждый apply — apply_catalog_change (внутренняя атомарность + baseline check
H6); внешняя transaction.atomic делает все 11 одной транзакцией: любой
не-applied результат → RuntimeError → откат всего.

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt06_apply.py', encoding='utf-8').read())"
"""

from django.db import transaction

from apps.catalog.models import CatalogChange, CatalogChangeStatus
from apps.catalog.processing import apply_catalog_change

RUN_ID = "00638eaa-0d7e-4532-b13f-ab40b3b8be0d"
EXPECTED = {
    4: "izm-areometry",
    22: "spetsialnye-klyuchi",
    123: "domkraty",
    164: "zaryadnye",
    179: "bp-kompressory",
    377: "sharoshki",
    422: "bp-vozdukhoduvki",
    4944: "yashchiki-sumki",
    4945: "krep-bolty",
    11232: "payalniki",
    23606: "hoz-himiya",
}

changes = list(
    CatalogChange.objects.filter(
        item__run_id=RUN_ID, status=CatalogChangeStatus.APPROVED
    ).select_related("item")
)
assert len(changes) == 11, f"ожидалось 11 approved changes, найдено {len(changes)}"
plan = {c.product_ref: c.proposed_value.get("option_slug") for c in changes}
assert plan == EXPECTED, f"план apply расходится с одобренным: {plan}"

results = {}
with transaction.atomic():
    for c in sorted(changes, key=lambda x: x.product_ref):
        # G1: change принадлежит именно этому run — перепроверка перед записью
        assert str(c.item.run_id) == RUN_ID, f"change {c.id} не из run {RUN_ID}"
        res = apply_catalog_change(c.id, actor_id=1)
        results[c.product_ref] = (c.proposed_value.get("option_slug"), res.status)
        if res.status != "applied":
            raise RuntimeError(f"apply failed for product {c.product_ref}: {res.status}")

for ref, (slug, st) in sorted(results.items()):
    print(f"  product={ref:6d} -> {slug:22s} {st}")
print("APPLIED_TOTAL:", sum(1 for _, st in results.values() if st == "applied"))
