# -*- coding: utf-8 -*-
"""CAT-02: проверка витрины — фасеты API против чисел из БД. READ-ONLY.

Дёргает реальный публичный эндпоинт ``/api/catalog/categories/<slug>/facets/``
тест-клиентом Django и сверяет каждое значение фасета с независимым COUNT по БД
(visible_products + attrs_cache). Плюс проверяет, что фильтр реально отсекает
выборку в листинге ``/api/catalog/products/``.

Вывод — JSON в $CAT02_OUT.
"""
import io
import json
import os

from django.db.models import Count
from django.db.models.fields.json import KeyTextTransform
from django.test import Client

from apps.catalog.filters import visible_products
from apps.catalog.models import Category

TARGETS = {
    "izmeritelnyy-ruletki": ["tape_length", "tape_width"],
    "izmeritelnyy-urovni": ["length"],
    "izmeritelnyy-shtangencirkuli-i-mikrometry": ["measuring_range", "readout_type"],
    "izmeritelnyy-ugolniki-i-lineyki": ["size"],
    "izmeritelnyy-dalnomery": ["max_distance"],
    "izmeritelnyy-lazernye-urovni-i-niveliry": ["level_type"],
    "izmeritelnyy-uglomery-i-uklonomery": ["size"],
}

c = Client(headers={"host": "dev.proff58.ru"}, secure=True)
out = {}
for cat_slug, attrs in TARGETS.items():
    url = f"/api/catalog/categories/{cat_slug}/facets/"
    r = c.get(url)
    entry = {"url": url, "status": r.status_code}
    if r.status_code != 200:
        entry["body"] = r.content.decode("utf-8", "replace")[:400]
        out[cat_slug] = entry
        continue
    data = r.json()
    entry["total_products"] = data["total_products"]
    entry["panels"] = [
        {
            "slug": f["slug"],
            "name": f["name"],
            "type": f["type"],
            "unit": f.get("unit"),
            "is_nav": f.get("is_nav"),
            "group": f.get("group"),
            "n_values": len(f["values"]),
            "sum_counts": sum(v["count"] for v in f["values"]),
        }
        for f in data["facets"]
    ]
    entry["panel_slugs"] = [f["slug"] for f in data["facets"]]

    # --- сверка каждого значения фасета с независимым COUNT по БД ---
    cat = Category.objects.get(slug=cat_slug)
    ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
    base = visible_products().filter(category_id__in=ids)
    checks = {}
    for a in attrs:
        panel = next((f for f in data["facets"] if f["slug"] == a), None)
        if panel is None:
            checks[a] = {"panel": "ОТСУТСТВУЕТ"}
            continue
        db_rows = dict(
            (r["_fv"], r["c"])
            for r in base.annotate(_fv=KeyTextTransform(a, "attrs_cache"))
            .filter(_fv__isnull=False)
            .values("_fv")
            .annotate(c=Count("id"))
        )
        api_rows = {}
        for v in panel["values"]:
            key = v["value"]
            # числовые фасеты API отдаёт float/int, в attrs_cache текст «400.0»
            api_rows[str(key)] = v["count"]
        norm_db = {}
        for k, n in db_rows.items():
            try:
                norm_db[str(float(k))] = n
            except (TypeError, ValueError):
                norm_db[str(k)] = n
        norm_api = {}
        for k, n in api_rows.items():
            try:
                norm_api[str(float(k))] = n
            except (TypeError, ValueError):
                norm_api[str(k)] = n
        checks[a] = {
            "api_values": len(norm_api),
            "db_values": len(norm_db),
            "api_sum": sum(norm_api.values()),
            "db_sum": sum(norm_db.values()),
            "match": norm_api == norm_db,
            "diff": {
                k: (norm_api.get(k), norm_db.get(k))
                for k in set(norm_api) | set(norm_db)
                if norm_api.get(k) != norm_db.get(k)
            },
        }
    entry["checks"] = checks
    out[cat_slug] = entry

# --- листинг реально отсекает выборку (range-фильтр) ---
listing = {}
for cat_slug, attr, lo in (
    ("izmeritelnyy-urovni", "length", 1000),
    ("izmeritelnyy-ruletki", "tape_length", 5),
    ("izmeritelnyy-ugolniki-i-lineyki", "size", 300),
):
    u0 = f"/api/catalog/products/?category={cat_slug}"
    u1 = f"{u0}&attr_{attr}_min={lo}"
    r0, r1 = c.get(u0), c.get(u1)
    cat = Category.objects.get(slug=cat_slug)
    ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
    base = visible_products().filter(category_id__in=ids)
    db_n = (
        base.annotate(_fv=KeyTextTransform(attr, "attrs_cache"))
        .filter(_fv__isnull=False)
        .count()
    )
    db_ge = 0
    for v in base.filter(attrs_cache__has_key=attr).values_list("attrs_cache", flat=True):
        try:
            if float(v.get(attr)) >= lo:
                db_ge += 1
        except (TypeError, ValueError):
            pass
    listing[f"{cat_slug}|{attr}>={lo}"] = {
        "url_all": u0,
        "url_filtered": u1,
        "api_all": r0.json().get("count") if r0.status_code == 200 else r0.status_code,
        "api_filtered": r1.json().get("count") if r1.status_code == 200 else r1.status_code,
        "db_with_attr": db_n,
        "db_ge": db_ge,
    }
out["_listing"] = listing

OUT = os.environ.get("CAT02_OUT", "/tmp/cat02_verify.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT)
