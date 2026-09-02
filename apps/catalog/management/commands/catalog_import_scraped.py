"""Импорт спарсенных характеристик в EAV (PARS-04, Phase 4).

    catalog_import_scraped <json> [<json> …] --category <slug> [--dry-run] [--limit N] [--report path]

- ``<json>`` — выгрузки парсера Phase 2 (``<source>.products.json``);
- ``--category`` — slug категории карты (``perforatory``): выбирает карту
  ``data/catalog_processing_rules/scraped_attr_map.<slug>.json`` и скоуп товаров
  (tool_type-опция с тем же slug);
- ``--dry-run`` — полный план БЕЗ единой записи (включая ImportRun);
- запись: транзакция на товар, ``source="scraper"``, перезапись по
  ``source_priority`` (manual/rules/import_1c не затираются), ``attrs_cache``
  пересобирается точечно по затронутым товарам.

Матчинг — ``(бренд, нормализованная модель)``, см. apps.catalog.scraped_import.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.contrib.postgres.search import TrigramSimilarity
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog import scraped_import as si
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductAttributeValue,
)

FUZZY_THRESHOLD = 0.4
FUZZY_TOP = 3


class Command(BaseCommand):
    help = "Импортировать спарсенные характеристики в EAV (scraper, с --dry-run план)."

    def add_arguments(self, parser):
        parser.add_argument("exports", nargs="+", help="JSON-выгрузки парсера Phase 2")
        parser.add_argument("--category", required=True, help="slug категории карты (perforatory)")
        parser.add_argument("--dry-run", action="store_true", help="план без единой записи")
        parser.add_argument("--limit", type=int, default=None, help="не более N карточек")
        parser.add_argument("--report", default=None, help="путь JSON-отчёта")
        parser.add_argument("--rules-path", default=None, help="каталог с attribute_rules.json")

    def handle(self, *args, **options):
        category = options["category"]
        base = Path(options["rules_path"] or data_dir())
        map_path = base / "catalog_processing_rules" / f"scraped_attr_map.{category}.json"
        if not map_path.exists():
            raise CommandError(f"Карта не найдена: {map_path}")
        amap = si.load_attr_map(map_path)
        model_prefixes = amap.get("model_prefixes")
        if model_prefixes:
            si.validate_model_prefixes(model_prefixes)

        rules_raw = json.loads((base / "attribute_rules.json").read_text(encoding="utf-8"))
        priority = rules_raw.get("source_priority", {})

        # карточки из выгрузок
        cards: list[tuple[str, dict]] = []
        for path in options["exports"]:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for card in data["products"]:
                cards.append((data["source"], card))
        if options["limit"]:
            cards = cards[: options["limit"]]

        # скоуп товаров: tool_type-опция == slug категории
        product_ids = list(
            ProductAttributeValue.objects.filter(
                attribute__slug="tool_type", value_option__slug=category
            ).values_list("product_id", flat=True)
        )
        products = list(Product.objects.filter(id__in=product_ids))
        index = si.build_product_index(products, prefixes=model_prefixes)

        # атрибуты и опции карты
        managed_slugs = {
            e["attribute"]
            for sdata in amap["sources"].values()
            for e in list(sdata["fields"].values())
            + sdata.get("fallbacks", [])
            + sdata.get("derived", [])
            if e.get("action", "map") == "map" or "attribute" in e
        }
        attr_by_slug = {a.slug: a for a in Attribute.objects.filter(slug__in=managed_slugs)}
        missing = managed_slugs - set(attr_by_slug)
        if missing:
            raise CommandError(f"Атрибуты карты отсутствуют в БД: {sorted(missing)}")
        # Fail-closed сверка единиц карты с осями в БД (ДРФ-1440): «Мощность, кВт»
        # в ось «Вт» или «Вес, кг» в ось «г» без объявленного пересчёта — стоп.
        try:
            si.validate_attr_map_units(amap, attr_by_slug)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        option_index: dict[str, dict[str, AttributeOption]] = {}
        for opt in AttributeOption.objects.filter(attribute__slug__in=managed_slugs).select_related(
            "attribute"
        ):
            option_index.setdefault(opt.attribute.slug, {})[opt.slug] = opt

        # существующие PAV по управляемым атрибутам для всего скоупа
        existing_by_product: dict[int, dict[str, ProductAttributeValue]] = {}
        for pav in ProductAttributeValue.objects.filter(
            product_id__in=product_ids, attribute__slug__in=managed_slugs
        ).select_related("attribute", "value_option"):
            existing_by_product.setdefault(pav.product_id, {})[pav.attribute.slug] = pav

        products_by_id = {p.id: p for p in products}

        stats = Counter()
        report: dict = {
            "category": category,
            "dry_run": options["dry_run"],
            "cards_total": len(cards),
            "matched": [],
            "ambiguous": [],
            "not_found": [],
            "fuzzy_suggestions": [],
            "unmapped_attributes": {},
            "created": [],
            "confirmed": [],
            "conflicts": [],
            "skipped_voltage": [],
            "dropped": [],
        }
        unmapped_counter: Counter = Counter()
        plans_by_product: dict[int, list[si.PlanItem]] = {}

        card_matches: list[dict] = []

        for source, card in cards:
            stats["cards"] += 1
            extraction = si.extract_card_values(card, source, amap)
            unmapped_counter.update(extraction.unmapped)
            for field, raw, reason in extraction.dropped:
                report["dropped"].append(
                    {
                        "source": source,
                        "card": card["name"],
                        "field": field,
                        "raw": raw,
                        "reason": reason,
                    }
                )
                stats["dropped"] += 1

            m = si.match_card(card, source, index, prefixes=model_prefixes)
            if m.status == "not_found":
                stats["not_found"] += 1
                report["not_found"].append(
                    {
                        "source": source,
                        "card": card["name"],
                        "model_key": m.model_key,
                        "url": card.get("source_url"),
                    }
                )
                suggestions = self._fuzzy(card, source, product_ids)
                if suggestions:
                    report["fuzzy_suggestions"].append(
                        {"source": source, "card": card["name"], "candidates": suggestions}
                    )
                continue
            if m.status == "ambiguous":
                stats["ambiguous"] += 1
                report["ambiguous"].append(
                    {
                        "source": source,
                        "card": card["name"],
                        "model_key": m.model_key,
                        "candidates": [{"id": p.id, "name": p.name} for p in m.products],
                    }
                )
                continue

            product = m.products[0]
            art = si.article_check(product, card.get("manufacturer_sku"))
            report["matched"].append(
                {
                    "source": source,
                    "card": card["name"],
                    "product_id": product.id,
                    "product": product.name,
                    "model_key": m.model_key,
                    "matched_by": m.matched_by,
                    "article": art,
                }
            )
            items = si.plan_product_values(
                product, extraction.values, existing_by_product.get(product.id, {}), priority
            )
            card_matches.append(
                {
                    "product_id": product.id,
                    "source": source,
                    "card": card,
                    "matched_by": m.matched_by,
                    "items": items,
                }
            )

        # «Многие к одному» с учётом лестницы: более точный матч вытесняет более слабый.
        product_hits: dict[int, list[dict]] = {}
        for cm in card_matches:
            product_hits.setdefault(cm["product_id"], []).append(cm)

        match_by_product: dict[int, dict] = {}
        for product_id, hits in product_hits.items():
            if len(hits) == 1:
                keeper = hits[0]
            else:
                best_rank = min(si.LADDER_RANK[h["matched_by"]] for h in hits)
                best = [h for h in hits if si.LADDER_RANK[h["matched_by"]] == best_rank]
                if len(best) > 1:
                    plans_by_product.pop(product_id, None)
                    stats["ambiguous"] += len(hits)
                    report["ambiguous"].append(
                        {
                            "reason": "многие к одному: несколько карточек -> один товар",
                            "product_id": product_id,
                            "product": products_by_id[product_id].name,
                            "cards": [h["card"]["name"] for h in hits],
                        }
                    )
                    report["matched"] = [
                        e for e in report["matched"] if e["product_id"] != product_id
                    ]
                    continue
                keeper = best[0]
                for h in hits:
                    if h is keeper:
                        continue
                    stats["ambiguous"] += 1
                    report["ambiguous"].append(
                        {
                            "reason": "менее точный матч отброшен",
                            "source": h["source"],
                            "product_id": product_id,
                            "product": products_by_id[product_id].name,
                            "card": h["card"]["name"],
                            "matched_by": h["matched_by"],
                            "kept": keeper["card"]["name"],
                            "kept_matched_by": keeper["matched_by"],
                        }
                    )
                report["matched"] = [
                    e
                    for e in report["matched"]
                    if not (e["product_id"] == product_id and e["card"] != keeper["card"]["name"])
                ]
            plans_by_product.setdefault(product_id, []).extend(keeper["items"])
            match_by_product[product_id] = keeper

        stats["matched"] = len(report["matched"])

        # Статистика значений и поимённые списки — ПОСЛЕ разрешения коллизий.
        for product_id, items in plans_by_product.items():
            product = products_by_id[product_id]
            match_info = match_by_product.get(product_id, {})
            card = match_info.get("card", {})
            source = match_info.get("source", "")
            for item in items:
                stats[item.action] += 1
                if item.action == "create":
                    report["created"].append(
                        {
                            "product_id": product.id,
                            "product": product.name,
                            "attribute": item.attribute_slug,
                            "field": item.field,
                            "new": str(item.new_value),
                            "raw": item.raw,
                        }
                    )
                elif item.action == "conflict":
                    report["conflicts"].append(
                        {
                            "product_id": product.id,
                            "product": product.name,
                            "attribute": item.attribute_slug,
                            "field": item.field,
                            "catalog_value": str(item.old_value),
                            "catalog_source": item.old_source,
                            "catalog_article": product.article,
                            "scraped_value": str(item.new_value),
                            "scraped_sku": card.get("manufacturer_sku"),
                            "scraped_source": source,
                            "raw": item.raw,
                        }
                    )
                elif item.action == "confirm":
                    report["confirmed"].append(
                        {
                            "product_id": product.id,
                            "product": product.name,
                            "attribute": item.attribute_slug,
                            "field": item.field,
                            "value": str(item.new_value),
                            "source": item.old_source,
                            "raw": item.raw,
                        }
                    )
                elif item.action == "skipped_voltage":
                    report["skipped_voltage"].append(
                        {
                            "product_id": product.id,
                            "product": product.name,
                            "field": item.field,
                            "raw": item.raw,
                            "value": str(item.new_value),
                        }
                    )

        report["unmapped_attributes"] = dict(unmapped_counter.most_common())
        report["stats"] = dict(stats)

        written = 0
        run = None
        if not options["dry_run"]:
            run = ImportRun.objects.create(source="catalog_import_scraped")
            try:
                for product_id, items in plans_by_product.items():
                    with transaction.atomic():
                        written += si.apply_plan_items(
                            products_by_id[product_id], items, attr_by_slug, option_index
                        )
                run.status = ImportRunStatus.DONE
            except Exception as exc:  # noqa: BLE001
                run.status = ImportRunStatus.FAILED
                run.stats = {"error": str(exc), **dict(stats)}
                run.finished_at = timezone.now()
                run.save()
                raise
            run.stats = {"written_pav": written, **dict(stats)}
            run.finished_at = timezone.now()
            run.save()

        if options["report"]:
            Path(options["report"]).write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )

        mode = "DRY-RUN (записей не было)" if options["dry_run"] else f"ЗАПИСЬ (PAV: {written})"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}. Карточек: {stats['cards']}, matched: {stats['matched']}, "
                f"ambiguous: {stats['ambiguous']}, not_found: {stats['not_found']}. "
                f"Значения: create {stats['create']}, confirm {stats['confirm']}, "
                f"conflict {stats.get('conflict', 0)}, "
                f"skipped_voltage {stats['skipped_voltage']}, dropped {stats['dropped']}."
            )
        )
        return str(run.pk) if run else ""

    def _fuzzy(self, card: dict, source: str, product_ids: list[int]) -> list[dict]:
        """pg_trgm-подсказки для не найденных карточек (только отчёт, не база)."""
        token = si.card_brand_token(card, source)
        if not token:
            return []
        qs = (
            Product.objects.filter(id__in=product_ids, name__icontains=token)
            .annotate(sim=TrigramSimilarity("name", card["name"]))
            .filter(sim__gte=FUZZY_THRESHOLD)
            .order_by("-sim")[:FUZZY_TOP]
        )
        return [{"id": p.id, "name": p.name, "similarity": round(p.sim, 3)} for p in qs]
