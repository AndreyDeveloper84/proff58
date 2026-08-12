import re

SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]
# префиксы карт: dreli/perforatory == LEGACY, карта shlifmashiny в dev отсутствует
PREFIXES = {"dreli-shurupoverty": None, "perforatory": None, "shlifmashiny": None}

# диагностический (не боевой) поиск модельного токена в имени карточки
CAND_RE = re.compile(r"[A-ZА-ЯЁ]{1,4}[-\s]?\d[\dА-ЯЁA-Z/.,-]*", re.I)

out = {"scopes": {}}

for slug in SCOPES:
    pids = list(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )
    products = list(Product.objects.filter(id__in=pids).only("id", "name", "article"))
    index = si.build_product_index(products, prefixes=PREFIXES[slug])
    # нормализованные имена скоупа для диагностического поиска
    norm_names = [(p, si.norm_key(p.name)) for p in products]

    stat = Counter()
    recoverable = []
    for source, cards in CARDS.items():
        token = TOKEN_BY_SOURCE[source]
        for c in cards:
            card = {"name": c["name"], "brand": None, "manufacturer_sku": c["sku"]}
            m = si.match_card(card, source, index, prefixes=PREFIXES[slug])
            stat[f"{source}:{m.status}"] += 1
            if m.status != "not_found":
                continue
            # есть ли в скоупе товар, чьё имя содержит модельный токен карточки
            cands = {si.norm_key(x) for x in CAND_RE.findall(c["name"])}
            cands = {k for k in cands if len(k) >= 4}
            if not cands:
                stat[f"{source}:nf_no_model_token_in_card"] += 1
                continue
            hits = [p for p, nn in norm_names if any(k in nn for k in cands)]
            if not hits:
                stat[f"{source}:nf_no_product_in_scope"] += 1
                continue
            stat[f"{source}:nf_RECOVERABLE"] += 1
            p0 = hits[0]
            low = p0.name.lower()
            why = []
            if token not in low:
                why.append("no_brand_token_in_product_name")
            if si.model_key(p0.name, prefixes=PREFIXES[slug]) is None:
                why.append("product_model_not_extracted")
            if si.model_key(c["name"], prefixes=PREFIXES[slug]) is None:
                why.append("card_model_not_extracted")
            if si.norm_key(p0.article or "") != si.norm_key(c["sku"]):
                why.append("article_ne_sku")
            for w in why:
                stat[f"{source}:why_{w}"] += 1
            if len(recoverable) < 40:
                recoverable.append(
                    {
                        "source": source,
                        "sku": c["sku"],
                        "card": c["name"][:80],
                        "product_id": p0.id,
                        "product": p0.name[:80],
                        "product_article": p0.article,
                        "n_hits": len(hits),
                        "why": why,
                    }
                )
    out["scopes"][slug] = {
        "scope_products": len(products),
        "indexed": len(index.entries),
        "stats": dict(stat),
        "recoverable": recoverable,
    }

print("PARS17_JSON_START")
print(json.dumps(out, ensure_ascii=True))
print("PARS17_JSON_END")
