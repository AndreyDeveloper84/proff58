SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]

scope_ids = set()
for slug in SCOPES:
    scope_ids |= set(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )

allp = list(Product.objects.only("id", "name", "article").iterator(chunk_size=5000))
index = si.build_product_index(allp, prefixes=None)

stat = Counter()
outside = []
for source, cards in CARDS.items():
    for c in cards:
        card = {"name": c["name"], "brand": None, "manufacturer_sku": c["sku"]}
        m = si.match_card(card, source, index, prefixes=None)
        stat[f"{source}:{m.status}"] += 1
        if m.status != "matched":
            continue
        p = m.products[0]
        stat[f"{source}:by_{m.matched_by}"] += 1
        if p.id in scope_ids:
            stat[f"{source}:in_map_scope"] += 1
        else:
            stat[f"{source}:outside_map_scope"] += 1
            if len(outside) < 25:
                outside.append(
                    {
                        "source": source,
                        "sku": c["sku"],
                        "card": c["name"][:70],
                        "product": p.name[:70],
                        "by": m.matched_by,
                    }
                )

print("PARS17_JSON_START")
print(
    json.dumps(
        {
            "catalog_products": len(allp),
            "indexed": len(index.entries),
            "scope_products": len(scope_ids),
            "stats": dict(stat),
            "outside_samples": outside,
        },
        ensure_ascii=True,
    )
)
print("PARS17_JSON_END")
