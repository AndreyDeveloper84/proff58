"""ПАРС-17 шаг 1 (read-only): где теряются товары при построении индекса.

Запуск: docker exec -i proff58_staging-web-1 python manage.py shell < p17_diag1.py
Пишет только JSON в stdout, в БД не пишет.
"""

import json
import re
from collections import Counter

from apps.catalog import scraped_import as si
from apps.catalog.models import Product, ProductAttributeValue

SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]
TOKENS = list(si.BRAND_TOKEN_BY_SOURCE.values())

# латинские написания тех же четырёх брендов
LATIN = {
    "ресанта": ["resanta"],
    "вихрь": ["vihr", "vikhr", "vihr'"],
    "интерскол": ["interskol"],
    "зубр": ["zubr"],
}

out = {"scopes": {}, "tokens": TOKENS}

for slug in SCOPES:
    pids = list(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )
    prods = list(Product.objects.filter(id__in=pids).only("id", "name", "article", "brand"))
    total = len(prods)
    indexed = []
    lost = []
    for p in prods:
        low = p.name.lower()
        if any(t in low for t in TOKENS):
            indexed.append(p)
        else:
            lost.append(p)
    # почему потеряны
    latin_hit = Counter()
    for p in lost:
        low = p.name.lower()
        for tok, alts in LATIN.items():
            if any(a in low for a in alts):
                latin_hit[tok] += 1
    # первое «брендовое» слово в потерянных именах: слово из >=3 букв в верхнем регистре
    # или слово, начинающееся с заглавной, кроме первого
    words = Counter()
    for p in lost:
        for w in re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\.\-]{2,}", p.name):
            words[w.lower()] += 1
    out["scopes"][slug] = {
        "total": total,
        "indexed": len(indexed),
        "lost": len(lost),
        "lost_pct": round(100.0 * len(lost) / total, 1) if total else 0,
        "lost_with_article": sum(1 for p in lost if (p.article or "").strip()),
        "indexed_with_article": sum(1 for p in indexed if (p.article or "").strip()),
        "lost_latin_brand": dict(latin_hit),
        "lost_top_words": words.most_common(25),
        "brand_field_nonempty": sum(1 for p in prods if (p.brand or "").strip()),
        "lost_sample": [
            {"id": p.id, "name": p.name, "article": p.article} for p in lost[:15]
        ],
    }

# общий срез: сколько вообще товаров в каталоге содержат токен бренда
allp = Product.objects.count()
out["catalog_total"] = allp
out["catalog_brand_field_nonempty"] = Product.objects.exclude(brand="").count()

print("PARS17_JSON_START")
print(json.dumps(out, ensure_ascii=True))
print("PARS17_JSON_END")
