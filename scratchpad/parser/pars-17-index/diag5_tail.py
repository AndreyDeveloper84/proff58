import re

SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]

# артикул производителя в имени товара: «72/14/4», «75/3/3» — отдельным токеном,
# не как часть модели («ЭШМ-125/5Э» → отбрасывается по предшествующему дефису)
NAME_SKU_RE = re.compile(r"(?<![\w/\-])\d{2,4}(?:/\d{1,4}){1,4}(?![\w/])")

out = {"scopes": {}}

for slug in SCOPES:
    pids = set(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )
    products = list(Product.objects.filter(id__in=pids).only("id", "name", "article"))
    index = si.build_product_index(products, prefixes=None)

    stat = Counter()
    extra = defaultdict(list)  # (token, key) -> entries
    samples = []
    for e in index.entries:
        p = e.product
        found = NAME_SKU_RE.findall(p.name)
        if not found:
            continue
        stat["indexed_with_name_sku"] += 1
        for raw in found:
            k = si.norm_key(raw)
            if not k:
                continue
            if e.article_key and k == e.article_key:
                stat["name_sku_equals_article"] += 1
                continue
            stat["name_sku_new_key"] += 1
            if not e.article_key:
                stat["name_sku_on_product_without_article"] += 1
            extra[(e.token, k)].append(e)
            if len(samples) < 15:
                samples.append(
                    {"id": p.id, "name": p.name[:80], "article": p.article, "name_sku": raw}
                )

    # какие карточки поймала бы расширенная ступень SKU
    gained = []
    gained_ambig = 0
    for source, cards in CARDS.items():
        token = TOKEN_BY_SOURCE[source]
        for c in cards:
            card = {"name": c["name"], "brand": None, "manufacturer_sku": c["sku"]}
            m = si.match_card(card, source, index, prefixes=None)
            if m.status != "not_found":
                continue
            for key in si._card_sku_keys(card):
                cands = extra.get((token, key), [])
                if not cands:
                    continue
                if len(cands) > 1:
                    gained_ambig += 1
                else:
                    gained.append(
                        {
                            "source": source,
                            "sku": c["sku"],
                            "card": c["name"][:80],
                            "product_id": cands[0].product.id,
                            "product": cands[0].product.name[:80],
                            "product_article": cands[0].product.article,
                        }
                    )
                break
    out["scopes"][slug] = {
        "scope_products": len(products),
        "indexed": len(index.entries),
        "stats": dict(stat),
        "extra_keys": len(extra),
        "gained": gained,
        "gained_ambiguous": gained_ambig,
        "samples": samples,
    }

print("PARS17_JSON_START")
print(json.dumps(out, ensure_ascii=True))
print("PARS17_JSON_END")
