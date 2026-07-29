# -*- coding: utf-8 -*-
"""CAT-09 S3 (ящики/контейнеры): rollback-map по ЯВНЫМ id + предсказание. READ-ONLY.

Сплит утверждён владельцем 2026-07-29: 59 товаров = 45 ящиков [214] (без 28109
«сырково-творожный» — пищевая тара) + 14 контейнеров хранения.
Исключены (остаются в prochaya-osnastka): 13 мусор/мед/нефтепродукты (нет типа),
26654 крышка, 27278 ремень (аксессуары), 27909/27910 тележки (→ obor-telezhki в S4),
26582 кубик 500мл + 28109 (пищевая тара), 26612/26613 баки 120л.
Пишет /tmp/cat09-s3-rollback.json (в контейнере). В БД не пишет.
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import AttributeOption  # noqa: E402
from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

IDS = [
    # 45 ящиков [214] (28107..28152 без 28109)
    *[i for i in range(28107, 28153) if i != 28109],
    # 14 контейнеров хранения
    26583, 26584, 26585, 26586, 26587,
    26598, 26599, 26600, 26601, 26602, 26603,
    26609, 26610, 26614,
]
assert len(IDS) == 59, len(IDS)

opt_old = AttributeOption.objects.get(attribute__slug="tool_type", slug="prochaya-osnastka")
opt_new = AttributeOption.objects.get(attribute__slug="tool_type", slug="yashchiki-sumki")

rollback = {}
errors = []
names = {p.id: p.name for p in Product.objects.filter(id__in=IDS)}
if len(names) != len(IDS):
    errors.append(f"не все id найдены: {sorted(set(IDS) - set(names))}")
for pid in IDS:
    pav = PAV.objects.filter(product_id=pid, attribute__slug="tool_type").first()
    if pav is None or pav.value_option_id != opt_old.id:
        errors.append(f"{pid}: option {pav.value_option_id if pav else None} != {opt_old.id}")
        continue
    rollback[str(pid)] = {
        "old_option_id": opt_old.id,
        "new_option_id": opt_new.id,
        "old_slug": "prochaya-osnastka",
        "new_slug": "yashchiki-sumki",
    }
if errors:
    raise SystemExit("PRECHECK FAILED:\n" + "\n".join(errors))

with io.open("/tmp/cat09-s3-rollback.json", "w", encoding="utf-8") as f:
    json.dump(rollback, f, ensure_ascii=False, indent=1)

pub = Product.objects.filter(id__in=IDS, is_active=True, status="published").count()


def cnt(slug, published=False):
    pids = PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug=slug
    ).values_list("product_id", flat=True)
    q = Product.objects.filter(id__in=pids)
    if published:
        q = q.filter(is_active=True, status="published")
    return q.count()


pav_total = PAV.objects.filter(attribute__slug="tool_type").count()

print(json.dumps({
    "old_option_id": opt_old.id,
    "new_option_id": opt_new.id,
    "ids_count": len(IDS),
    "pub_in_cluster": pub,
    "predict": {
        "yashchiki-sumki_total": [cnt("yashchiki-sumki"), cnt("yashchiki-sumki") + len(IDS)],
        "yashchiki-sumki_pub": [cnt("yashchiki-sumki", True), cnt("yashchiki-sumki", True) + pub],
        "prochaya_total": [cnt("prochaya-osnastka"), cnt("prochaya-osnastka") - len(IDS)],
        "prochaya_pub": [cnt("prochaya-osnastka", True), cnt("prochaya-osnastka", True) - pub],
        "pav_total": [pav_total, pav_total],
    },
}, ensure_ascii=False))
