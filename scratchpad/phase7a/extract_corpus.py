import hashlib, json, os, tempfile
from django.db import connection, transaction
from django.utils import timezone
from apps.catalog.models import CatalogChange, ProductAttributeValue
from apps.catalog.processing import canonical_hash

OUT = "/app/logs/applied_corpus_tool_type.v1.json"

with transaction.atomic():
    with connection.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    extracted_at = timezone.now().isoformat()
    applied = (CatalogChange.objects
               .filter(status="applied", target_kind="tool_type")
               .order_by("product_ref", "applied_at", "pk"))
    by_product = {}
    for ch in applied:
        by_product.setdefault(ch.product_ref, []).append(ch)

    pav_by_product = {
        p.product_id: p
        for p in (ProductAttributeValue.objects
                  .filter(product_id__in=list(by_product),
                          attribute__slug="tool_type",
                          value_option__isnull=False)
                  .select_related("value_option", "product"))
    }
    items, collisions, exclusions = [], 0, []
    for pid in sorted(by_product):
        changes = by_product[pid]
        pav = pav_by_product.get(pid)
        if pav is None:
            exclusions.append({"product_id": pid, "reason": "no_current_pav"})
            continue
        slug = pav.value_option.slug
        if any((c.after_value or {}).get("option_slug") != slug for c in changes):
            collisions += 1
        current = next(
            (c for c in reversed(changes)
             if (c.after_value or {}).get("option_slug") == slug),
            None,
        )
        if current is None:
            exclusions.append({"product_id": pid,
                               "reason": "no_provenance_for_current_label"})
            continue
        p = pav.product
        facts = {"name": p.name or "", "original_name": p.original_name or "",
                 "brand": p.brand or "", "source_group": p.source_group or "",
                 "article": p.article or ""}
        items.append({
            "product_id": pid, "change_id": str(current.pk), "pav_id": pav.pk,
            "source": pav.source or "", "confidence": pav.confidence,
            "applied_at": current.applied_at.isoformat() if current.applied_at else "",
            "applied_option_slug": slug, **facts,
            "facts_hash": canonical_hash(facts),
        })
    # corpus_id — content-addressed (review P0-1): уникален и воспроизводим.
    # Считается ДО вставки по содержимому без volatile extracted_at:
    # одинаковые данные → одинаковый corpus_id при любом перезапуске.
    doc = {"version": 1, "extracted_at": extracted_at, "source": "staging",
           "counters": {
               "raw_applied_changes": sum(len(v) for v in by_product.values()),
               "distinct_products": len(by_product),
               "current_label_corpus": len(items),
               "historical_label_collisions": collisions,
           },
           "items": items}
    content_hash = canonical_hash({k: v for k, v in doc.items() if k != "extracted_at"})
    doc["corpus_id"] = f"staging-tool-type-{content_hash[:12]}"
    payload = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir="/app/logs", prefix="corpus.", suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(payload.encode("utf-8"))
    os.replace(tmp, OUT)
    print("corpus_id:", doc["corpus_id"])
    print("counters:", json.dumps(doc["counters"], sort_keys=True))
    print("exclusions:", json.dumps(exclusions, ensure_ascii=False))
    print("corpus_hash:", canonical_hash({k: v for k, v in doc.items() if k != "extracted_at"}))
    print("sha256:", hashlib.sha256(payload.encode("utf-8")).hexdigest())
