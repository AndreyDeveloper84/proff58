"""ПАРС-17 шаг 4 (read-only): усечённые написания брендов и многобрендовые имена."""

import json
import re
from collections import Counter

from apps.catalog import scraped_import as si
from apps.catalog.models import Product, ProductAttributeValue

TOKENS = list(si.BRAND_TOKEN_BY_SOURCE.values())

# стем -> полный токен; стем ловит усечения 1С («ВИХР», «РЕСАНТ», «ИНТЕРСК»)
STEMS = {
    "ресант": "ресанта",
    "вихр": "вихрь",
    "интерск": "интерскол",
    "зубр": "зубр",
}
LATIN = {"resanta": "ресанта", "vihr": "вихрь", "vikhr": "вихрь",
         "interskol": "интерскол", "zubr": "зубр"}

SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]

out = {}


def analyse(products, label):
    full = Counter()
    stem_only = Counter()
    latin_only = Counter()
    multi = 0
    stem_samples = []
    latin_samples = []
    multi_samples = []
    for p in products:
        low = p.name.lower()
        hits = [t for t in TOKENS if t in low]
        if len(hits) > 1:
            multi += 1
            if len(multi_samples) < 8:
                multi_samples.append({"id": p.id, "name": p.name, "tokens": hits})
        for t in hits:
            full[t] += 1
        if hits:
            continue
        for stem, tok in STEMS.items():
            if stem in low:
                stem_only[tok] += 1
                if len(stem_samples) < 15:
                    stem_samples.append({"id": p.id, "name": p.name, "stem": stem})
                break
        else:
            for lat, tok in LATIN.items():
                if re.search(r"\b" + lat, low):
                    latin_only[tok] += 1
                    if len(latin_samples) < 15:
                        latin_samples.append({"id": p.id, "name": p.name, "lat": lat})
                    break
    return {
        "label": label,
        "total": len(products),
        "with_full_token": sum(1 for p in products if any(t in p.name.lower() for t in TOKENS)),
        "full_by_token": dict(full),
        "stem_only": dict(stem_only),
        "latin_only": dict(latin_only),
        "multi_token": multi,
        "stem_samples": stem_samples,
        "latin_samples": latin_samples,
        "multi_samples": multi_samples,
    }


allp = list(Product.objects.only("id", "name").iterator(chunk_size=5000))
out["catalog"] = analyse(allp, "catalog")

for slug in SCOPES:
    pids = set(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )
    out[slug] = analyse([p for p in allp if p.id in pids], slug)

print("PARS17_JSON_START")
print(json.dumps(out, ensure_ascii=True))
print("PARS17_JSON_END")
