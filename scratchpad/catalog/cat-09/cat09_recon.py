# -*- coding: utf-8 -*-
"""CAT-09: разведка кластеров prochaya-osnastka. READ-ONLY, ни одной записи."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402


def type_pids(slug):
    return set(
        PAV.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )


def pub_of(qs):
    return qs.filter(is_active=True, status="published").count()


out = {}

# --- prochaya-osnastka: база ---
proch_pids = type_pids("prochaya-osnastka")
proch_qs = Product.objects.filter(id__in=proch_pids)
out["prochaya_total"] = proch_qs.count()
out["prochaya_pub"] = pub_of(proch_qs)

# --- смазки ---
smaz = list(
    proch_qs.filter(name__icontains="смазка")
    .select_related("category")
    .order_by("id")
    .values("id", "name", "is_active", "status", "category_id")
)
out["smazki_total"] = len(smaz)
out["smazki_pub"] = sum(1 for r in smaz if r["is_active"] and r["status"] == "published")
out["smazki_names"] = smaz
# подозрительные: не начинаются со слова «смазка»
out["smazki_not_first_word"] = [
    r for r in smaz if not r["name"].lower().lstrip("яя ").startswith("смазк")
]
# смазка-подобные вне prochaya (контроль утечки критерия)
other_smaz = (
    Product.objects.filter(name__icontains="смазка")
    .exclude(id__in=proch_pids)
    .values_list("id", flat=True)
)
out["smazka_word_outside_prochaya"] = list(other_smaz)

# --- целевой тип str-smazki: что там сейчас ---
for slug in ("str-smazki", "lebedki-tali", "yashchiki-sumki", "obor-telezhki", "hoz-tachki"):
    pids = type_pids(slug)
    qs = Product.objects.filter(id__in=pids)
    out[f"{slug}_total"] = qs.count()
    out[f"{slug}_pub"] = pub_of(qs)

# --- тележки: вопрос владельца (obor-telezhki vs hoz-tachki) ---
for slug in ("obor-telezhki", "hoz-tachki"):
    pids = type_pids(slug)
    sample = list(
        Product.objects.filter(id__in=pids)
        .order_by("id")
        .values_list("name", flat=True)[:25]
    )
    out[f"{slug}_sample"] = sample

tel = list(
    proch_qs.filter(name__istartswith="тележк")
    .order_by("id")
    .values("id", "name", "is_active", "status", "category_id")
)
out["telezhki_total"] = len(tel)
out["telezhki_pub"] = sum(1 for r in tel if r["is_active"] and r["status"] == "published")
out["telezhki_names"] = tel

# --- лебёдки/тали: ^таль|^тельфер|^лебедк + категория 169 ---
import re  # noqa: E402

rx = re.compile(r"^(таль|тельфер|лебёдк|лебедк)", re.IGNORECASE)
leb = []
for r in (
    proch_qs.filter(category_id=169)
    .order_by("id")
    .values("id", "name", "is_active", "status", "category_id")
):
    if rx.match(r["name"].lstrip("яЯ ")):
        leb.append(r)
out["lebedki_total"] = len(leb)
out["lebedki_pub"] = sum(1 for r in leb if r["is_active"] and r["status"] == "published")
out["lebedki_names"] = leb
# категория 169 вне критерия по имени (что остаётся)
cat169_all = list(
    proch_qs.filter(category_id=169).order_by("id").values("id", "name")
)
out["cat169_not_matched"] = [r for r in cat169_all if not rx.match(r["name"].lstrip("яЯ "))]

# --- ящики: категория 214 + ^контейнер ---
ya = list(
    proch_qs.filter(category_id=214)
    .order_by("id")
    .values("id", "name", "is_active", "status", "category_id")
)
kont = list(
    proch_qs.filter(name__istartswith="контейнер")
    .order_by("id")
    .values("id", "name", "is_active", "status", "category_id")
)
seen = {r["id"] for r in ya}
merged = ya + [r for r in kont if r["id"] not in seen]
out["yashchiki_total"] = len(merged)
out["yashchiki_pub"] = sum(1 for r in merged if r["is_active"] and r["status"] == "published")
out["yashchiki_names"] = merged
out["konteyner_extra"] = [r for r in kont if r["id"] not in seen]

print(json.dumps(out, ensure_ascii=False, default=str))
