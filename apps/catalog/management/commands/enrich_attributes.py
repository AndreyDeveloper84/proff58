"""Извлечение и простановка характеристик товаров (Фаза B, #96).

Для каждого товара берём его ``tool_type`` из ``attrs_cache`` (проставлен
``enrich_tool_type``), извлекаем характеристики движком ``attribute_extract`` и
делаем upsert ``ProductAttributeValue`` — но только если источник вправе
перезаписать прежний (``source_priority.can_overwrite``): ручные и 1С-значения
неприкосновенны. ``attrs_cache`` — read-model, пересобираем здесь же (bulk).

Bulk-паттерн как в ``enrich_tool_type`` (#93): без per-row update_or_create,
иначе шторм запросов и сигналов на ~16k товарах.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.attribute_extract import (
    KIND_BOOLEAN,
    KIND_NUMBER,
    KIND_SELECT,
    AttributeRules,
    ExtractedValue,
)
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductAttributeValue,
)
from apps.catalog.source_priority import can_overwrite
from apps.catalog.tool_type import normalize

BATCH = 1000
PAV_UPDATE_FIELDS = ["value_decimal", "value_boolean", "value_option", "source", "confidence"]
TOOL_TYPE_SLUG = "tool_type"


class Command(BaseCommand):
    help = "Проставить характеристики по attribute_rules.json (идемпотентно, с провенансом)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules = AttributeRules.from_file(f"{base}/attribute_rules.json")

        attr_by_slug = {a.slug: a for a in Attribute.objects.all()}
        missing = self._missing_attributes(rules, attr_by_slug)
        if missing:
            self.stderr.write(
                f"Не найдены характеристики {sorted(missing)} — выполните load_attributes."
            )
            return ""

        option_index = self._option_index(rules, attr_by_slug)
        attr_ids = {attr_by_slug[s].id for s in self._rule_slugs(rules)}
        existing_pav = {
            (pav.product_id, pav.attribute_id): pav
            for pav in ProductAttributeValue.objects.filter(attribute_id__in=attr_ids)
        }

        run = ImportRun.objects.create(source="enrich_attributes")
        stats: dict[str, int] = {
            "processed": 0,
            "values_set": 0,
            "skipped_protected": 0,
            "no_attributes": 0,
        }

        pav_create: list[ProductAttributeValue] = []
        pav_update: list[ProductAttributeValue] = []
        cache_updates: list[Product] = []

        qs = Product.objects.exclude(category__isnull=True).iterator(chunk_size=2000)
        try:
            with transaction.atomic():
                for product in qs:
                    tool_type = (product.attrs_cache or {}).get(TOOL_TYPE_SLUG)
                    if not tool_type or rules.get(tool_type) is None:
                        continue
                    stats["processed"] += 1

                    name = product.original_name or product.name
                    extracted = rules.extract_all(tool_type, name)
                    if not extracted:
                        stats["no_attributes"] += 1
                        continue

                    cache = dict(product.attrs_cache or {})
                    changed = False
                    for ev in extracted:
                        attribute = attr_by_slug[ev.spec.slug]
                        applied = self._apply_value(
                            product,
                            attribute,
                            ev,
                            existing_pav,
                            option_index,
                            pav_create,
                            pav_update,
                            stats,
                        )
                        if applied is not None:
                            cache[ev.spec.slug] = applied
                            changed = True

                    if changed:
                        product.attrs_cache = cache
                        cache_updates.append(product)

                    self._flush(pav_create, pav_update, cache_updates, force=False)

                self._flush(pav_create, pav_update, cache_updates, force=True)
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
        self.stdout.write(
            self.style.SUCCESS(
                f"Характеристики: обработано {stats['processed']}, "
                f"значений проставлено {stats['values_set']}, "
                f"защищённых пропущено {stats['skipped_protected']}, "
                f"без характеристик {stats['no_attributes']}."
            )
        )
        return str(run.pk)

    # --- применение одного значения --------------------------------------

    def _apply_value(
        self, product, attribute, ev: ExtractedValue, existing_pav, option_index, pav_create,
        pav_update, stats,
    ):
        """Upsert PAV с учётом приоритета источника. Возвращает JSON-значение для
        attrs_cache, либо None если значение не записано (защищено/нет опции)."""
        pav = existing_pav.get((product.id, attribute.id))
        if pav is not None and not can_overwrite(pav.source, ev.source):
            stats["skipped_protected"] += 1
            return None

        option = None
        if ev.spec.kind == KIND_SELECT:
            option = option_index.get(attribute.id, {}).get(normalize(ev.option_value))
            if option is None:
                return None  # вариант не загружен — пропускаем

        if pav is None:
            pav = ProductAttributeValue(product=product, attribute=attribute)
            self._set_fields(pav, ev, option)
            pav_create.append(pav)
            existing_pav[(product.id, attribute.id)] = pav
        else:
            self._set_fields(pav, ev, option)
            pav_update.append(pav)

        stats["values_set"] += 1
        return self._cache_value(ev, option)

    @staticmethod
    def _set_fields(pav: ProductAttributeValue, ev: ExtractedValue, option) -> None:
        pav.value_decimal = ev.decimal if ev.spec.kind == KIND_NUMBER else None
        pav.value_boolean = ev.boolean if ev.spec.kind == KIND_BOOLEAN else None
        pav.value_option = option
        pav.source = ev.source
        pav.confidence = ev.confidence

    @staticmethod
    def _cache_value(ev: ExtractedValue, option):
        if ev.spec.kind == KIND_NUMBER:
            return ev.decimal
        if ev.spec.kind == KIND_BOOLEAN:
            return ev.boolean
        return option.value if option is not None else None

    # --- bulk-сброс ------------------------------------------------------

    @staticmethod
    def _flush(pav_create, pav_update, cache_updates, *, force: bool) -> None:
        if force or len(pav_create) >= BATCH:
            ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
            pav_create.clear()
        if force or len(pav_update) >= BATCH:
            ProductAttributeValue.objects.bulk_update(
                pav_update, PAV_UPDATE_FIELDS, batch_size=BATCH
            )
            pav_update.clear()
        if force or len(cache_updates) >= BATCH:
            Product.objects.bulk_update(cache_updates, ["attrs_cache"], batch_size=BATCH)
            cache_updates.clear()

    # --- индексы ---------------------------------------------------------

    @staticmethod
    def _rule_slugs(rules: AttributeRules) -> set[str]:
        return {spec.slug for tt in rules.tool_types for spec in tt.attributes}

    def _missing_attributes(self, rules, attr_by_slug) -> set[str]:
        return {s for s in self._rule_slugs(rules) if s not in attr_by_slug}

    @staticmethod
    def _option_index(rules, attr_by_slug) -> dict[int, dict[str, AttributeOption]]:
        select_ids = [
            attr_by_slug[spec.slug].id
            for tt in rules.tool_types
            for spec in tt.attributes
            if spec.kind == KIND_SELECT
        ]
        index: dict[int, dict[str, AttributeOption]] = {}
        for opt in AttributeOption.objects.filter(attribute_id__in=select_ids):
            index.setdefault(opt.attribute_id, {})[normalize(opt.value)] = opt
        return index
