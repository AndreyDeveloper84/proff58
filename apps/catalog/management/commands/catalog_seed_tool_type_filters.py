"""Закрепить фильтры tool_type ЛОКАЛЬНО на узлах-типах (инвариант «узел несёт фасеты»).

Проблема (§3.7). ``load_attributes`` биндит атрибуты tool_type к КОРНЮ по имени
(``category="Ручной инструмент"`` → CategoryAttribute на корне), а
``_category_filter_attributes`` наследует фильтры ВНИЗ по предкам (closest-wins). При
реструктуризации узел-тип уезжает в use-раздел (напр. «Домкраты» → «Автоинструмент и
гаражное оборудование»), цепочка предков меняется, корень-источник из неё выпадает →
фильтры (``capacity``/``domkrat_type``) на странице типа исчезают.

Решение. Для каждого узла, где у товаров ПРЕОБЛАДАЕТ один ``tool_type``, ставим атрибуты
этого типа как ``CategoryAttribute`` прямо на сам узел. Тогда closest-wins берёт их из
себя — фильтры переживают любой перенос. Источник правил — ``data/attribute_rules.json``
(тот же, что у ``load_attributes``); ``Attribute`` должны быть уже созданы им.

    ./manage.py catalog_seed_tool_type_filters             # dry-run
    ./manage.py catalog_seed_tool_type_filters --commit     # применить

Идемпотентно (``update_or_create``). Запускать после реструктуризации (переноса
узлов-типов). По умолчанию узел считается «типом», если один tool_type покрывает
≥ ``--dominance`` товаров поддерева и таких товаров ≥ ``--min-products``.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    Category,
    CategoryAttribute,
    ProductAttributeValue,
)

TOOL_TYPE_SLUG = "tool_type"


class Command(BaseCommand):
    help = "Локально закрепить фильтры tool_type на узлах-типах (инвариант переноса фасетов)."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")
        parser.add_argument(
            "--min-products",
            type=int,
            default=5,
            help="Минимум товаров с преобладающим tool_type, чтобы считать узел типом.",
        )
        parser.add_argument(
            "--dominance",
            type=float,
            default=0.5,
            help="Доля товаров преобладающего tool_type (0..1) для срабатывания.",
        )

    def handle(self, *args, **options):
        rules = json.loads((Path(data_dir()) / "attribute_rules.json").read_text(encoding="utf-8"))
        # registry: tool_type slug -> [(attr_slug, is_filter, is_seo_facet)]
        registry: dict[str, list[tuple[str, bool, bool]]] = {}
        for tt in rules.get("tool_types", []):
            specs = [
                (a["slug"], a.get("is_filter", True), a.get("is_seo_facet", False))
                for a in tt.get("attributes", [])
                if a.get("slug") and a["slug"] != TOOL_TYPE_SLUG
            ]
            if specs:
                registry[tt["tool_type"]] = specs

        attrs_by_slug = {a.slug: a for a in Attribute.objects.all()}
        min_products = options["min_products"]
        dominance = options["dominance"]

        # plan: (category, tool_type, specs, dom_count, total)
        plan: list[tuple[Category, str, list[tuple[str, bool, bool]], int, int]] = []
        for cat in Category.objects.filter(is_site_v2=True):
            sub = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
            counts: Counter[str] = Counter()
            for row in (
                ProductAttributeValue.objects.filter(
                    product__category_id__in=sub, attribute__slug=TOOL_TYPE_SLUG
                )
                .values("value_option__slug")
                .annotate(n=Count("id"))
            ):
                slug = row["value_option__slug"]
                if slug:
                    counts[slug] = row["n"]
            if not counts:
                continue
            dom_slug, dom_n = counts.most_common(1)[0]
            total = sum(counts.values())
            if dom_n < min_products or dom_n < dominance * total:
                continue
            specs = registry.get(dom_slug)
            if specs:
                plan.append((cat, dom_slug, specs, dom_n, total))

        self._report(plan)
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit.")
            )
            return

        stamped = 0
        with transaction.atomic():
            for cat, _dom_slug, specs, _dn, _t in plan:
                for attr_slug, is_filter, is_seo in specs:
                    attribute = attrs_by_slug.get(attr_slug)
                    if attribute is None:
                        self.stdout.write(
                            self.style.WARNING(f"  атрибут {attr_slug} не найден — пропуск")
                        )
                        continue
                    CategoryAttribute.objects.update_or_create(
                        category=cat,
                        attribute=attribute,
                        defaults={"is_filter": is_filter, "is_seo_facet": is_seo},
                    )
                    stamped += 1
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: закреплено привязок {stamped} на {len(plan)} узлах-типах."
            )
        )

    def _report(self, plan):
        w = self.stdout.write
        w(
            self.style.MIGRATE_HEADING(
                "\n=== Закрепление фильтров tool_type на узлах-типах (dry-run) ==="
            )
        )
        for cat, dom_slug, specs, dn, total in sorted(plan, key=lambda r: -r[3]):
            parent = cat.get_parent()
            w(
                f"  «{cat.name}» (id={cat.pk}, под «{parent.name if parent else '—'}») "
                f"tool_type={dom_slug} {dn}/{total} → {[s[0] for s in specs]}"
            )
        w(self.style.SUCCESS(f"\nИТОГО узлов-типов: {len(plan)}."))
