out = {}

# --- 1. индекс каталога по нормализованному артикулу -------------------------
by_article = defaultdict(list)
qs = Product.objects.exclude(article="").only("id", "name", "article")
n_products = 0
for p in qs.iterator(chunk_size=5000):
    n_products += 1
    k = si.norm_key(p.article)
    if k:
        by_article[k].append(p)
out["catalog_products_with_article"] = n_products
out["catalog_distinct_article_keys"] = len(by_article)

# --- 2. скоупы карт -----------------------------------------------------------
SCOPES = ["dreli-shurupoverty", "perforatory", "shlifmashiny"]
scope_ids = {}
for slug in SCOPES:
    scope_ids[slug] = set(
        ProductAttributeValue.objects.filter(
            attribute__slug="tool_type", value_option__slug=slug
        ).values_list("product_id", flat=True)
    )
all_scope_ids = set().union(*scope_ids.values())


def has_token(name, token):
    return token in name.lower()


def any_token(name):
    low = name.lower()
    return next((t for t in TOKENS if t in low), None)


# --- 3. сверка карточек с артикулами ------------------------------------------
per_source = {}
for source, cards in CARDS.items():
    token = TOKEN_BY_SOURCE[source]
    stat = Counter()
    lost_examples = []
    kept_examples = []
    foreign_examples = []
    collisions = []
    for c in cards:
        keys = si.norm_key(c["sku"])
        if not keys:
            stat["sku_empty"] += 1
            continue
        hits = by_article.get(keys, [])
        if not hits:
            stat["no_product_with_such_article"] += 1
            continue
        stat["article_hit"] += 1
        if len(hits) > 1:
            stat["article_hit_multi"] += 1
            collisions.append(
                {"sku": c["sku"], "products": [{"id": p.id, "name": p.name} for p in hits[:4]]}
            )
        with_tok = [p for p in hits if has_token(p.name, token)]
        without_tok = [p for p in hits if not has_token(p.name, token)]
        if with_tok:
            stat["hit_with_own_token"] += 1
            if len(kept_examples) < 5:
                kept_examples.append({"sku": c["sku"], "product": with_tok[0].name})
        if without_tok and not with_tok:
            stat["hit_only_without_token"] += 1
            other = any_token(without_tok[0].name)
            if other:
                stat["hit_without_token_but_other_brand_token"] += 1
                if len(foreign_examples) < 10:
                    foreign_examples.append(
                        {
                            "sku": c["sku"],
                            "card": c["name"][:90],
                            "product": without_tok[0].name,
                            "other_token": other,
                        }
                    )
            else:
                stat["hit_without_any_token"] += 1
                if len(lost_examples) < 20:
                    lost_examples.append(
                        {
                            "sku": c["sku"],
                            "card": c["name"][:90],
                            "product_id": without_tok[0].id,
                            "product": without_tok[0].name,
                            "in_scope": without_tok[0].id in all_scope_ids,
                        }
                    )
            # в скоупе ли карт
            if any(p.id in all_scope_ids for p in without_tok):
                stat["lost_in_map_scope"] += 1
    per_source[source] = {
        "cards": len(cards),
        "stats": dict(stat),
        "kept_examples": kept_examples,
        "lost_examples": lost_examples,
        "foreign_brand_examples": foreign_examples,
        "collisions": collisions[:10],
    }
out["per_source"] = per_source

print("PARS17_JSON_START")
print(json.dumps(out, ensure_ascii=True))
print("PARS17_JSON_END")
