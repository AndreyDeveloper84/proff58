"""Извлечение характеристик товара (EAV) из названия 1С — Фаза B (#96).

Зеркало ``enrich_tool_type`` поверх движка #99 (`attribute_extract.AttributeRules`):

1. tool_type товара берём из его PAV (``value_option.slug``), НЕ из attrs_cache
   (там русский ярлык). По slug движок знает правила (`rules_for`).
2. ``rules.extract(slug, name)`` → список значений; каждое пишем в
   ``ProductAttributeValue`` (number→value_decimal, select→value_option, boolean→value_boolean).
3. Провенанс: ``source`` (regex/keyword/…) и ``confidence``. Перезапись разрешена
   только если приоритет нового источника ≥ приоритета сохранённого
   (``rules.source_priority``) — ручное (manual) и 1С не затираются regex/keyword.
   ``confidence`` в решении о перезаписи НЕ участвует.
4. Bulk-паттерн #93: префетч PAV → ``iterator`` → ``bulk_create``/``bulk_update``
   батчами; ``attrs_cache`` обновляем в памяти; итоги — в ``ImportRun.stats``.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.attribute_extract import BOOLEAN, NUMBER, SELECT, AttributeRules
from apps.catalog.attrs_cache import flush_attrs_cache_merged
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductAttributeValue,
    Source,
)
from apps.catalog.read_models import extracted_value_to_json

BATCH = 1000
TOOL_TYPE_SLUG = "tool_type"

# Источники, которыми владеет движок: их устаревшие значения можно удалять при
# повторном enrich. manual/import_1c (авторитетные) и llm (отдельный проход) — НЕ трогаем.
PRUNABLE_SOURCES = frozenset({Source.REGEX, Source.KEYWORD, Source.INFERRED})

# Уверенность по источнику (только аналитика/AI, НЕ участвует в overwrite).
SOURCE_CONFIDENCE = {
    Source.MANUAL: 100,
    Source.IMPORT_1C: 100,
    Source.REGEX: 100,
    Source.KEYWORD: 90,
    Source.SCRAPER: 90,
    Source.LLM: 60,
}

# Поля значения PAV, пересобираемые при записи (фиксированный список для bulk_update).
VALUE_FIELDS = ["value_text", "value_integer", "value_decimal", "value_boolean", "value_option"]
UPDATE_FIELDS = VALUE_FIELDS + ["source", "confidence"]


class Command(BaseCommand):
    help = "Извлечь характеристики из названий и записать в EAV (идемпотентно, bulk)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        raw = json.loads(Path(f"{base}/attribute_rules.json").read_text(encoding="utf-8"))
        rules = AttributeRules.from_dict(raw)
        priority = rules.source_priority

        tt_slugs = [tt["tool_type"] for tt in raw.get("tool_types", [])]
        managed_slugs = {a["slug"] for tt in raw.get("tool_types", []) for a in tt["attributes"]}
        # slug'и атрибутов, которыми движок управляет в рамках каждого tool_type
        # (для идемпотентной чистки — чужие типы не задеваем).
        managed_by_tt = {
            tt["tool_type"]: {a["slug"] for a in tt["attributes"]}
            for tt in raw.get("tool_types", [])
        }

        attr_by_slug = {a.slug: a for a in Attribute.objects.filter(slug__in=managed_slugs)}
        missing = managed_slugs - set(attr_by_slug)
        if missing:
            self.stderr.write(
                f"Не найдены атрибуты {sorted(missing)} — сначала выполните load_attributes."
            )
            return ""

        # Опции select-характеристик: {attr_slug: {option_slug: AttributeOption}}.
        option_index: dict[str, dict[str, AttributeOption]] = {}
        for opt in AttributeOption.objects.filter(attribute__slug__in=managed_slugs).select_related(
            "attribute"
        ):
            option_index.setdefault(opt.attribute.slug, {})[opt.slug] = opt

        # product_id → slug его tool_type (только товары интересующих типов).
        product_tt = {
            row["product_id"]: row["value_option__slug"]
            for row in ProductAttributeValue.objects.filter(
                attribute__slug=TOOL_TYPE_SLUG,
                value_option__isnull=False,
                value_option__slug__in=tt_slugs,
            ).values("product_id", "value_option__slug")
        }
        product_ids = list(product_tt)

        # Существующие PAV управляемых атрибутов — объектами (bulk_update + проверка приоритета).
        existing: dict[tuple[int, str], ProductAttributeValue] = {}
        for pav in ProductAttributeValue.objects.filter(
            product_id__in=product_ids, attribute__slug__in=managed_slugs
        ).select_related("attribute"):
            existing[(pav.product_id, pav.attribute.slug)] = pav

        run = ImportRun.objects.create(source="enrich_attributes")
        stats = {
            "processed": 0,
            "no_attributes": 0,
            "by_attribute": {},
            "skipped_priority": 0,
            "pruned": {},
        }

        pav_create: list[ProductAttributeValue] = []
        pav_update: list[ProductAttributeValue] = []
        pav_delete_ids: list[int] = []
        cache_updates: list[Product] = []

        # Ключи attrs_cache, которыми владеет команда для конкретного товара (его
        # tool_type). Нужно для безопасной записи: чужие ключи не трогаем (#5).
        def managed_for(product: Product) -> set[str]:
            return set(managed_by_tt.get(product_tt.get(product.id, ""), ()))

        qs = Product.objects.filter(id__in=product_ids).iterator(chunk_size=2000)
        try:
            with transaction.atomic():
                for product in qs:
                    stats["processed"] += 1
                    tt_slug = product_tt[product.id]
                    name = product.original_name or product.name
                    values = rules.extract(tt_slug, name)
                    current = {av.slug for av in values}

                    cache = dict(product.attrs_cache or {})
                    cache_changed = False

                    # Идемпотентность: убрать engine-значения, которых движок больше
                    # не извлекает (устаревший regex/keyword/inferred). Авторитетные
                    # источники (manual/import_1c) и llm не трогаем.
                    for slug in managed_by_tt.get(tt_slug, ()):
                        if slug in current:
                            continue
                        pav = existing.get((product.id, slug))
                        if pav is None or pav.pk is None or pav.source not in PRUNABLE_SOURCES:
                            continue
                        pav_delete_ids.append(pav.pk)
                        existing.pop((product.id, slug), None)
                        if slug in cache:
                            del cache[slug]
                            cache_changed = True
                        stats["pruned"][slug] = stats["pruned"].get(slug, 0) + 1

                    if not values:
                        stats["no_attributes"] += 1

                    for av in values:
                        attribute = attr_by_slug[av.slug]
                        option = None
                        if av.kind == SELECT:
                            option = option_index.get(av.slug, {}).get(av.option_slug)
                            if option is None:
                                continue  # вариант не загружен — пропускаем
                        new_source = av.source
                        new_conf = SOURCE_CONFIDENCE.get(new_source, 100)
                        key = (product.id, av.slug)
                        pav = existing.get(key)

                        if pav is None:
                            pav = ProductAttributeValue(
                                product=product,
                                attribute=attribute,
                                source=new_source,
                                confidence=new_conf,
                            )
                            self._apply_value(pav, av, option)
                            pav_create.append(pav)
                            existing[key] = pav
                        else:
                            # Перезапись только если приоритет нового ≥ сохранённого.
                            if priority.get(new_source, 0) < priority.get(pav.source, 0):
                                stats["skipped_priority"] += 1
                                continue
                            pav.source = new_source
                            pav.confidence = new_conf
                            self._apply_value(pav, av, option)
                            pav_update.append(pav)

                        cache[av.slug] = extracted_value_to_json(attribute, av, option)
                        cache_changed = True
                        stats["by_attribute"][av.slug] = stats["by_attribute"].get(av.slug, 0) + 1

                    if cache_changed:
                        product.attrs_cache = cache
                        cache_updates.append(product)

                    if len(pav_delete_ids) >= BATCH:
                        ProductAttributeValue.objects.filter(id__in=pav_delete_ids).delete()
                        pav_delete_ids.clear()
                    if len(pav_create) >= BATCH:
                        ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                        pav_create.clear()
                    if len(pav_update) >= BATCH:
                        ProductAttributeValue.objects.bulk_update(
                            pav_update, UPDATE_FIELDS, batch_size=BATCH
                        )
                        pav_update.clear()
                    if len(cache_updates) >= BATCH:
                        flush_attrs_cache_merged(cache_updates, managed_for, batch_size=BATCH)
                        cache_updates.clear()

                if pav_delete_ids:
                    ProductAttributeValue.objects.filter(id__in=pav_delete_ids).delete()
                if pav_create:
                    ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                if pav_update:
                    ProductAttributeValue.objects.bulk_update(
                        pav_update, UPDATE_FIELDS, batch_size=BATCH
                    )
                if cache_updates:
                    flush_attrs_cache_merged(cache_updates, managed_for, batch_size=BATCH)

                run.status = ImportRunStatus.DONE
        except Exception as exc:  # noqa: BLE001
            run.status = ImportRunStatus.FAILED
            stats["error"] = str(exc)
            run.finished_at = timezone.now()
            run.stats = stats
            run.save()
            raise

        run.finished_at = timezone.now()
        run.stats = stats
        run.save()

        by_attr = ", ".join(f"{k}: {v}" for k, v in sorted(stats["by_attribute"].items()))
        pruned_total = sum(stats["pruned"].values())
        pruned_detail = (
            " (" + ", ".join(f"{k}: {v}" for k, v in sorted(stats["pruned"].items())) + ")"
            if stats["pruned"]
            else ""
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Характеристики: обработано {stats['processed']}, "
                f"без характеристик {stats['no_attributes']}, "
                f"пропущено по приоритету {stats['skipped_priority']}, "
                f"удалено устаревших {pruned_total}{pruned_detail}. По атрибутам — {by_attr}."
            )
        )
        return str(run.pk)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _apply_value(pav: ProductAttributeValue, av, option) -> None:
        """Записать значение в нужное поле PAV, очистив остальные."""
        pav.value_text = ""
        pav.value_integer = None
        pav.value_decimal = None
        pav.value_boolean = None
        pav.value_option = None
        if av.kind == NUMBER:
            pav.value_decimal = av.number
        elif av.kind == SELECT:
            pav.value_option = option
        elif av.kind == BOOLEAN:
            pav.value_boolean = av.boolean
