"""Замер ДО/ПОСЛЕ: индекс с многотокенным входом + артикул из имени + отсев РСВ."""

import re

GARBAGE_ARTICLE_PREFIXES = ("РСВ",)
NAME_SKU_RE = re.compile(r"(?<![\w/\-])\d{2,4}(?:/\d{1,4}){2,4}(?![\w/])")
TOKEN_ORDER = list(dict.fromkeys(si.BRAND_TOKEN_BY_SOURCE.values()))


def new_tokens(p):
    low = p.name.lower()
    return [t for t in TOKEN_ORDER if t in low]


def new_article_keys(p):
    keys = []
    art = (p.article or "").strip()
    if art and not art.upper().startswith(GARBAGE_ARTICLE_PREFIXES):
        k = si.norm_key(art)
        if k:
            keys.append(k)
    for raw in NAME_SKU_RE.findall(p.name):
        k = si.norm_key(raw)
        if k and k not in keys:
            keys.append(k)
    return keys


def build_new(products, prefixes=None):
    idx = si.MatchIndex()
    for p in products:
        toks = new_tokens(p)
        if not toks:
            continue
        exact = si._exact_model_key(p.name, prefixes=prefixes)
        normalized = si.model_key(p.name, prefixes=prefixes)
        alias = si._alias_key(si.extract_model(p.name, prefixes=prefixes)) if exact else None
        akeys = new_article_keys(p)
        e = si.ProductMatchEntry(
            product=p,
            token=toks[0],
            exact_key=exact,
            normalized_key=normalized,
            alias_key=alias,
            article_key=akeys[0] if akeys else None,
        )
        idx.entries.append(e)
        for t in toks:
            idx.by_token[t].append(e)
            for k in akeys:
                idx.by_article[(t, k)].append(e)
            if exact:
                idx.by_exact[(t, exact)].append(e)
            if normalized:
                idx.by_normalized[(t, normalized)].append(e)
            if alias:
                idx.by_alias[(t, alias)].append(e)
    return idx


def run(index, label):
    stat = Counter()
    got = {}
    for source, cards in CARDS.items():
        for c in cards:
            card = {"name": c["name"], "brand": None, "manufacturer_sku": c["sku"]}
            m = si.match_card(card, source, index, prefixes=None)
            stat[m.status] += 1
            if m.status == "matched":
                stat["by_" + m.matched_by] += 1
                got[(source, c["sku"])] = (m.products[0].id, m.products[0].name, m.matched_by)
    return {
        "label": label,
        "entries": len(index.entries),
        "article_keys": len(index.by_article),
        "stats": dict(stat),
    }, got


SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]
out = {"scopes": {}}

allp = list(Product.objects.only("id", "name", "article").iterator(chunk_size=5000))

scope_sets = {
    slug: set(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )
    for slug in SCOPES
}
groups = [("catalog", allp)] + [
    (slug, [p for p in allp if p.id in scope_sets[slug]]) for slug in SCOPES
]

for label, prods in groups:
    old = si.build_product_index(prods, prefixes=None)
    new = build_new(prods, prefixes=None)
    r_old, g_old = run(old, "before")
    r_new, g_new = run(new, "after")
    delta_new = [
        {"source": k[0], "sku": k[1], "product": v[1][:70], "by": v[2]}
        for k, v in g_new.items()
        if k not in g_old
    ]
    delta_lost = [
        {"source": k[0], "sku": k[1], "product": v[1][:70], "by": v[2]}
        for k, v in g_old.items()
        if k not in g_new
    ]
    changed = [
        {"source": k[0], "sku": k[1], "before": g_old[k][1][:60], "after": v[1][:60]}
        for k, v in g_new.items()
        if k in g_old and g_old[k][0] != v[0]
    ]
    out["scopes"][label] = {
        "before": r_old,
        "after": r_new,
        "gained": delta_new,
        "lost": delta_lost,
        "changed_target": changed,
        "scope_products": len(prods),
    }

# диагностика: какие ключи добавил артикул-из-имени по всему каталогу
samples = []
n_extra = 0
for p in allp:
    if not new_tokens(p):
        continue
    found = NAME_SKU_RE.findall(p.name)
    if not found:
        continue
    n_extra += 1
    if len(samples) < 60:
        samples.append({"name": p.name[:80], "article": p.article, "found": found})
out["name_sku_products"] = n_extra
out["name_sku_samples"] = samples

# сколько артикулов отсеяно как мусорные РСВ
out["garbage_article_products"] = sum(
    1
    for p in allp
    if (p.article or "").strip().upper().startswith(GARBAGE_ARTICLE_PREFIXES) and new_tokens(p)
)

print("PARS17_JSON_START")
print(json.dumps(out, ensure_ascii=True))
print("PARS17_JSON_END")
