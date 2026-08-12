# -*- coding: utf-8 -*-
"""CAT-05 · задача 1: аудит «данные есть — фильтра нет» по всему каталогу. READ-ONLY.

Один проход по опубликованным товарам (attrs_cache — то, из чего строятся фасеты),
свёртка по дереву категорий снизу вверх. Для каждой категории и каждого управляемого
атрибута: сколько опубликованных товаров поддерева несёт значение, доля, число
различных значений, есть ли эффективная панель (CategoryAttribute в цепочке с
is_filter=True и attribute.is_filterable=True). Мёртвый груз — значения в категориях,
чья цепочка панели не имеет.

Вывод — JSON в $CAT05_OUT.
"""
import io
import json
import os
from collections import defaultdict

from apps.catalog.ingest import data_dir
from apps.catalog.models import Attribute, Category, CategoryAttribute, Product

raw = json.load(open(f"{data_dir()}/attribute_rules.json", encoding="utf-8"))
managed = sorted({a["slug"] for tt in raw.get("tool_types", []) for a in tt["attributes"]})
mset = set(managed) - {"tool_type"}  # tool_type — навигационная панель, не кандидат

filterable = set(Attribute.objects.filter(is_filterable=True).values_list("slug", flat=True))

cats = {}
by_path = {}
for c in Category.objects.all():
    cats[c.pk] = c
    by_path[c.path] = c
STEP = Category.steplen
parent_of = {}
children_of = defaultdict(list)
for c in cats.values():
    p = by_path.get(c.path[:-STEP]) if len(c.path) > STEP else None
    parent_of[c.pk] = p.pk if p else None
    if p:
        children_of[p.pk].append(c.pk)

# Эффективные панели: атрибуты цепочки (категория + предки) с двойным гейтом.
ca_by_cat = defaultdict(set)
for row in CategoryAttribute.objects.filter(is_filter=True).values_list(
    "category_id", "attribute__slug"
):
    ca_by_cat[row[0]].add(row[1])
ca_by_cat = {k: {a for a in v if a in filterable} for k, v in ca_by_cat.items()}

def chain_attrs(cat_id):
    out = set()
    cid = cat_id
    while cid is not None:
        out |= ca_by_cat.get(cid, set())
        cid = parent_of[cid]
    return out

# Прямые счётчики по опубликованным.
direct_pub = defaultdict(int)
attr_n = defaultdict(lambda: defaultdict(int))          # cat -> attr -> товаров с атр.
attr_vals = defaultdict(lambda: defaultdict(set))       # cat -> attr -> distinct значения
qs = Product.objects.filter(is_active=True, status="published").values_list(
    "category_id", "attrs_cache"
)
for cat_id, cache in qs.iterator():
    if cat_id is None:
        continue
    direct_pub[cat_id] += 1
    for a in mset & set((cache or {}).keys()):
        attr_n[cat_id][a] += 1
        attr_vals[cat_id][a].add(str(cache[a]))

# Свёртка в поддерево (снизу вверх по глубине).
sub_pub = defaultdict(int)
sub_attr_n = defaultdict(lambda: defaultdict(int))
sub_attr_vals = defaultdict(lambda: defaultdict(set))
for c in sorted(cats.values(), key=lambda x: -x.depth):
    sub_pub[c.pk] += direct_pub[c.pk]
    for a, n in attr_n[c.pk].items():
        sub_attr_n[c.pk][a] += n
        sub_attr_vals[c.pk][a] |= attr_vals[c.pk][a]
    p = parent_of[c.pk]
    if p is not None:
        sub_pub[p] += sub_pub[c.pk]
        for a, n in sub_attr_n[c.pk].items():
            sub_attr_n[p][a] += n
            sub_attr_vals[p][a] |= sub_attr_vals[c.pk][a]

# Строки аудита по категориям (только категории с опубликованными).
rows = []
for c in sorted(cats.values(), key=lambda x: x.path):
    if sub_pub[c.pk] == 0:
        continue
    panel = chain_attrs(c.pk)
    attrs_out = {}
    for a in sorted(sub_attr_n[c.pk]):
        n = sub_attr_n[c.pk][a]
        attrs_out[a] = {
            "n": n,
            "share": round(100.0 * n / sub_pub[c.pk], 1),
            "distinct": len(sub_attr_vals[c.pk][a]),
            "panel": a in panel,
            "filterable": a in filterable,
        }
    rows.append(
        {
            "slug": c.slug,
            "name": c.name,
            "depth": c.depth,
            "parent": cats[parent_of[c.pk]].slug if parent_of[c.pk] else None,
            "pub_subtree": sub_pub[c.pk],
            "attrs": attrs_out,
        }
    )

# Мёртвый груз по прямым счётчикам (значение без панели в своей цепочке),
# свёрнутый на корни разделов.
dead_root = defaultdict(lambda: defaultdict(int))
filled_root = defaultdict(lambda: defaultdict(int))
for c in cats.values():
    # корень раздела: предок глубины 1 (или сама категория, если она корень)
    cid, root_id = c.pk, c.pk
    while parent_of[root_id] is not None:
        root_id = parent_of[root_id]
    panel = chain_attrs(c.pk)
    for a, n in attr_n[c.pk].items():
        filled_root[root_id][a] += n
        if a not in panel:
            dead_root[root_id][a] += n

roots = []
for c in sorted((x for x in cats.values() if parent_of[x.pk] is None), key=lambda x: x.name):
    dead = sum(dead_root[c.pk].values())
    filled = sum(filled_root[c.pk].values())
    roots.append(
        {
            "slug": c.slug,
            "name": c.name,
            "pub_subtree": sub_pub[c.pk],
            "filled_values": filled,
            "dead_values": dead,
            "dead_by_attr": {a: n for a, n in sorted(dead_root[c.pk].items(), key=lambda t: -t[1])},
        }
    )
roots.sort(key=lambda r: -r["dead_values"])

OUT = os.environ.get("CAT05_OUT", "/tmp/cat05_audit.json")
io.open(OUT, "w", encoding="utf-8").write(
    json.dumps(
        {"managed": managed, "filterable": sorted(filterable), "roots": roots, "categories": rows},
        ensure_ascii=False,
        default=str,
    )
)
print("WROTE", OUT, "roots:", len(roots), "categories:", len(rows))
