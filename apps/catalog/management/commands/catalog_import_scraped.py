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
        index = si.build_product_index(products)

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
            "overwritten": [],
            "skipped_priority": [],
            "skipped_voltage": [],
            "dropped": [],
        }
        unmapped_counter: Counter = Counter()
        plans_by_product: dict[int, list[si.PlanItem]] = {}
        product_cards: dict[int, list[str]] = {}

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

            m = si.match_card(card, source, index)
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
                    "article": art,
                }
            )
            product_cards.setdefault(product.id, []).append(card["name"])
            items = si.plan_product_values(
                product, extraction.values, existing_by_product.get(product.id, {}), priority
            )
            plans_by_product.setdefault(product.id, []).extend(items)

        # «Многие к одному»: несколько карточек → один товар — в отчёт, не в базу.
        for product_id, names in list(product_cards.items()):
            if len(names) < 2:
                continue
            plans_by_product.pop(product_id, None)
            stats["ambiguous"] += len(names)
            report["ambiguous"].append(
                {
                    "reason": "многие к одному: несколько карточек -> один товар",
                    "product_id": product_id,
                    "product": products_by_id[product_id].name,
                    "cards": names,
                }
            )
            report["matched"] = [e for e in report["matched"] if e["product_id"] != product_id]
        stats["matched"] = len(report["matched"])

        # Статистика значений и поимённые списки — ПОСЛЕ разрешения коллизий.
        for product_id, items in plans_by_product.items():
            product = products_by_id[product_id]
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
                elif item.action == "overwrite":
                    report["overwritten"].append(
                        {
                            "product_id": product.id,
                            "product": product.name,
                            "attribute": item.attribute_slug,
                            "field": item.field,
                            "old": str(item.old_value),
                            "new": str(item.new_value),
                            "old_source": item.old_source,
                            "raw": item.raw,
                        }
                    )
                elif item.action == "skipped_priority":
                    report["skipped_priority"].append(
                        {
                            "product_id": product.id,
                            "product": product.name,
                            "attribute": item.attribute_slug,
                            "field": item.field,
                            "current": str(item.old_value),
                            "current_source": item.old_source,
                            "rejected": str(item.new_value),
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
                f"overwrite {stats['overwrite']}, skipped_priority {stats['skipped_priority']}, "
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
