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

Режим ``--dry-run``/``--report-only`` (окно CODE-01): тот же extraction/write-decision
path, что и боевой apply — решения (create/update/keep/prune/skip) принимает тот же
код, расходится только финальный шаг: вместо записи в БД каждое решение попадает в
machine-readable JSON-отчёт (``--json-report <файл>``, иначе stdout; человекочитаемая
сводка тогда идёт в stderr). Dry-run НЕ пишет PAV, НЕ меняет ``attrs_cache`` и НЕ
создаёт ``ImportRun``.

Граница выборки (окно ХАР-SCOPE): ``--tool-type`` / ``--category-id`` (оба
repeatable), ``--include-descendants``, ``--in-stock-only``. Фильтры складываются
**пересечением (AND)**: товар обязан быть в разрешённой ветке дерева И с ненулевым
остатком И его tool_type обязан входить в волну. Без новых флагов выборка прежняя —
все товары тех tool_type, для которых в ``attribute_rules.json`` есть блок правил.
Отбор строится ОДИН раз до расхождения dry-run/apply, поэтому оба режима работают по
одному и тому же набору ``product_id``.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.attribute_extract import BOOLEAN, NUMBER, SELECT, TEXT, AttributeRules
from apps.catalog.attrs_cache import flush_attrs_cache_merged
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Category,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductAttributeValue,
    Source,
)
from apps.catalog.read_models import attr_value_to_json, extracted_value_to_json

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


def resolve_category_ids(category_ids: list[int], include_descendants: bool) -> list[int]:
    """id категорий выборки: сами узлы, с ``include_descendants`` — плюс всё поддерево.

    Несуществующий id — ошибка (fail-closed): опечатка в номере категории иначе
    даёт молча пустую выборку, а оператор считает, что скоуп сработал.
    """
    categories = list(Category.objects.filter(pk__in=category_ids))
    missing = sorted(set(category_ids) - {category.pk for category in categories})
    if missing:
        raise CommandError(f"Категории не найдены: {missing}")
    resolved = {category.pk for category in categories}
    if include_descendants:
        for category in categories:
            resolved.update(category.get_descendants().values_list("pk", flat=True))
    return sorted(resolved)


class Command(BaseCommand):
    help = "Извлечь характеристики из названий и записать в EAV (идемпотентно, bulk)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")
        parser.add_argument(
            "--dry-run",
            "--report-only",
            dest="dry_run",
            action="store_true",
            help=(
                "Ничего не писать в БД (PAV/attrs_cache/ImportRun): построить "
                "machine-readable JSON-отчёт create/update/keep/prune/skip."
            ),
        )
        parser.add_argument(
            "--json-report",
            dest="json_report",
            default=None,
            help="Файл для machine-readable JSON-отчёта dry-run (иначе — stdout).",
        )
        parser.add_argument(
            "--tool-type",
            dest="tool_type",
            action="append",
            default=None,
            metavar="SLUG",
            help=(
                "Ограничить выборку типом инструмента (slug варианта tool_type). "
                "Можно указывать несколько раз. Без флага — все типы, описанные "
                "правилами."
            ),
        )
        parser.add_argument(
            "--category-id",
            dest="category_id",
            action="append",
            type=int,
            default=None,
            metavar="ID",
            help="Ограничить выборку категорией. Можно указывать несколько раз.",
        )
        parser.add_argument(
            "--include-descendants",
            dest="include_descendants",
            action="store_true",
            help="Вместе с --category-id: захватить все категории-потомки.",
        )
        parser.add_argument(
            "--in-stock-only",
            dest="in_stock_only",
            action="store_true",
            help="Только товары в наличии (available_quantity > 0).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        json_report_path = options["json_report"]
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

        # --- граница выборки (ХАР-SCOPE): tool_type AND дерево AND остаток -----
        requested_tt = sorted(set(options["tool_type"] or ()))
        category_ids = sorted(set(options["category_id"] or ()))
        include_descendants = options["include_descendants"]
        in_stock_only = options["in_stock_only"]

        if include_descendants and not category_ids:
            raise CommandError("--include-descendants требует --category-id.")

        selected_tt = tt_slugs
        if requested_tt:
            unknown = sorted(set(requested_tt) - set(tt_slugs))
            if unknown:
                # Не ошибка: в манифесте типов кратно больше, чем блоков правил.
                # Такой тип просто не даёт товаров в выборку — предупреждаем, чтобы
                # оператор не принял пустой прогон за «нечего обогащать».
                self.stderr.write(
                    f"Типы без блока правил в attribute_rules.json: {unknown} — "
                    "товары этих типов в выборку не попадут."
                )
            selected_tt = [slug for slug in tt_slugs if slug in set(requested_tt)]

        resolved_category_ids = (
            resolve_category_ids(category_ids, include_descendants) if category_ids else []
        )

        # Фильтры по самому товару (дерево + остаток) — пересечением с типом.
        # Наличие: available_quantity > 0. Канонического хелпера «в наличии» в
        # проекте нет: витрина (queries.products_in, filters.filter_in_stock)
        # считает по stock_quantity, а операционные команды каталога
        # (catalog_queue_create --in-stock, catalog_rules_shadow, catalog_v2_report)
        # и Product.recalc_stock_status — по available_quantity. Здесь операционный
        # контур, поэтому берём available_quantity, как у соседних команд.
        product_scope: dict[str, object] = {}
        if resolved_category_ids:
            product_scope["category_id__in"] = resolved_category_ids
        if in_stock_only:
            product_scope["available_quantity__gt"] = 0

        # product_id → slug его tool_type (только товары интересующих типов).
        tt_values = ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG,
            value_option__isnull=False,
            value_option__slug__in=selected_tt,
        )
        if product_scope:
            tt_values = tt_values.filter(
                product_id__in=Product.objects.filter(**product_scope).values("pk")
            )
        product_tt = {
            row["product_id"]: row["value_option__slug"]
            for row in tt_values.values("product_id", "value_option__slug")
        }
        product_ids = list(product_tt)

        scope = {
            "tool_types": requested_tt,
            "category_ids": category_ids,
            "include_descendants": include_descendants,
            "in_stock_only": in_stock_only,
            "resolved_category_ids": resolved_category_ids,
            "selected_tool_types": sorted(selected_tt),
            "selected_products": len(product_ids),
        }

        # Существующие PAV управляемых атрибутов — объектами (bulk_update + проверка приоритета).
        # value_option нужен dry-run'у для current_value (attr_value_to_json) без N+1.
        existing: dict[tuple[int, str], ProductAttributeValue] = {}
        for pav in ProductAttributeValue.objects.filter(
            product_id__in=product_ids, attribute__slug__in=managed_slugs
        ).select_related("attribute", "value_option"):
            existing[(pav.product_id, pav.attribute.slug)] = pav

        run = None if dry_run else ImportRun.objects.create(source="enrich_attributes")
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
        # По-позиционные решения dry-run (только в режиме отчёта).
        report_rows: list[dict] = []

        # Ключи attrs_cache, которыми владеет команда для конкретного товара (его
        # tool_type). Нужно для безопасной записи: чужие ключи не трогаем (#5).
        def managed_for(product: Product) -> set[str]:
            return set(managed_by_tt.get(product_tt.get(product.id, ""), ()))

        # Строка по-позиционного отчёта dry-run; в боевом режиме — no-op.
        def add_report_row(
            product: Product,
            tt_slug: str,
            action: str,
            slug: str,
            current_value,
            proposed_value,
            source_fragment: str,
            source: str,
            reason: str,
        ) -> None:
            if not dry_run:
                return
            report_rows.append(
                {
                    "product_id": product.id,
                    "tool_type": tt_slug,
                    "attribute": slug,
                    "current_value": current_value,
                    "proposed_value": proposed_value,
                    "source_fragment": source_fragment,
                    "action": action,
                    "reason": reason,
                    "source": source,
                }
            )

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
                        if pav is None or pav.pk is None:
                            continue
                        if pav.source not in PRUNABLE_SOURCES:
                            # Авторитетный/чужой источник по управляемому атрибуту,
                            # который движок не извлёк: решение «оставить как есть».
                            add_report_row(
                                product,
                                tt_slug,
                                "keep",
                                slug,
                                attr_value_to_json(pav),
                                None,
                                "",
                                pav.source,
                                f"источник {pav.source} вне PRUNABLE_SOURCES — "
                                "движок не управляет, значение остаётся",
                            )
                            continue
                        add_report_row(
                            product,
                            tt_slug,
                            "prune",
                            slug,
                            attr_value_to_json(pav),
                            None,
                            "",
                            pav.source,
                            f"движок больше не извлекает значение; источник {pav.source} "
                            "из PRUNABLE_SOURCES — устаревшее значение удаляется",
                        )
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
                                # вариант не загружен — пропускаем
                                pav0 = existing.get((product.id, av.slug))
                                add_report_row(
                                    product,
                                    tt_slug,
                                    "skip",
                                    av.slug,
                                    attr_value_to_json(pav0) if pav0 is not None else None,
                                    av.option_value,
                                    av.matched,
                                    av.source,
                                    f"вариант {av.option_slug!r} не загружен — "
                                    "выполните load_attributes",
                                )
                                continue
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
                            add_report_row(
                                product,
                                tt_slug,
                                "create",
                                av.slug,
                                None,
                                extracted_value_to_json(attribute, av, option),
                                av.matched,
                                new_source,
                                "PAV отсутствует — значение создаётся",
                            )
                            pav_create.append(pav)
                            existing[key] = pav
                            cache[av.slug] = extracted_value_to_json(attribute, av, option)
                            cache_changed = True
                        else:
                            old_source = pav.source
                            # Перезапись только если приоритет нового ≥ сохранённого.
                            if priority.get(new_source, 0) < priority.get(old_source, 0):
                                stats["skipped_priority"] += 1
                                add_report_row(
                                    product,
                                    tt_slug,
                                    "skip",
                                    av.slug,
                                    attr_value_to_json(pav),
                                    extracted_value_to_json(attribute, av, option),
                                    av.matched,
                                    new_source,
                                    f"приоритет {new_source} ({priority.get(new_source, 0)}) "
                                    f"< {old_source} ({priority.get(old_source, 0)}) — "
                                    "перезапись запрещена",
                                )
                                continue

                            value_changed = self._value_changed(pav, av, option)
                            source_changed = new_source != old_source

                            if not value_changed and not source_changed:
                                add_report_row(
                                    product,
                                    tt_slug,
                                    "keep",
                                    av.slug,
                                    attr_value_to_json(pav),
                                    extracted_value_to_json(attribute, av, option),
                                    av.matched,
                                    new_source,
                                    "значение не изменилось — PAV остаётся без перезаписи",
                                )
                                continue

                            current_value = attr_value_to_json(pav) if dry_run else None
                            pav.source = new_source
                            pav.confidence = new_conf
                            self._apply_value(pav, av, option)
                            if not value_changed and source_changed:
                                reason = (
                                    f"значение не изменилось, но источник {new_source} "
                                    f"({priority.get(new_source, 0)}) выше приоритетом, "
                                    f"чем {old_source} ({priority.get(old_source, 0)}) — "
                                    "обновление происхождения записи"
                                )
                            else:
                                reason = (
                                    f"приоритет {new_source} ({priority.get(new_source, 0)}) "
                                    f">= {old_source} ({priority.get(old_source, 0)}) — "
                                    "перезапись"
                                )
                            add_report_row(
                                product,
                                tt_slug,
                                "update",
                                av.slug,
                                current_value,
                                extracted_value_to_json(attribute, av, option),
                                av.matched,
                                new_source,
                                reason,
                            )
                            pav_update.append(pav)
                            cache[av.slug] = extracted_value_to_json(attribute, av, option)
                            cache_changed = True

                        stats["by_attribute"][av.slug] = stats["by_attribute"].get(av.slug, 0) + 1

                    if cache_changed:
                        product.attrs_cache = cache
                        cache_updates.append(product)

                    if not dry_run and len(pav_delete_ids) >= BATCH:
                        ProductAttributeValue.objects.filter(id__in=pav_delete_ids).delete()
                        pav_delete_ids.clear()
                    if not dry_run and len(pav_create) >= BATCH:
                        ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                        pav_create.clear()
                    if not dry_run and len(pav_update) >= BATCH:
                        ProductAttributeValue.objects.bulk_update(
                            pav_update, UPDATE_FIELDS, batch_size=BATCH
                        )
                        pav_update.clear()
                    if not dry_run and len(cache_updates) >= BATCH:
                        flush_attrs_cache_merged(cache_updates, managed_for, batch_size=BATCH)
                        cache_updates.clear()

                if not dry_run and pav_delete_ids:
                    ProductAttributeValue.objects.filter(id__in=pav_delete_ids).delete()
                if not dry_run and pav_create:
                    ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                if not dry_run and pav_update:
                    ProductAttributeValue.objects.bulk_update(
                        pav_update, UPDATE_FIELDS, batch_size=BATCH
                    )
                if not dry_run and cache_updates:
                    flush_attrs_cache_merged(cache_updates, managed_for, batch_size=BATCH)

                if run is not None:
                    run.status = ImportRunStatus.DONE
        except Exception as exc:  # noqa: BLE001
            if run is not None:
                run.status = ImportRunStatus.FAILED
                stats["error"] = str(exc)
                run.finished_at = timezone.now()
                run.stats = stats
                run.save()
            raise

        if run is not None:
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
        summary = (
            f"Характеристики: обработано {stats['processed']}, "
            f"без характеристик {stats['no_attributes']}, "
            f"пропущено по приоритету {stats['skipped_priority']}, "
            f"удалено устаревших {pruned_total}{pruned_detail}. По атрибутам — {by_attr}."
        )

        if requested_tt or category_ids or in_stock_only:
            summary += (
                f" Выборка: типы {scope['selected_tool_types'] or '—'}, "
                f"категории {resolved_category_ids or '—'}"
                f"{' (с потомками)' if include_descendants else ''}, "
                f"только в наличии: {'да' if in_stock_only else 'нет'} — "
                f"{scope['selected_products']} товаров."
            )

        if dry_run:
            self._emit_dry_run_report(
                report_rows,
                stats,
                summary,
                base=base,
                json_report_path=json_report_path,
                scope=scope,
            )
            # Вернуть непустую строку нельзя: BaseCommand.execute() автоматически
            # печатает возврат handle() в stdout и ломает чистый JSON.
            return ""

        self.stdout.write(self.style.SUCCESS(summary))
        return str(run.pk)

    # --- dry-run отчёт -----------------------------------------------------

    def _emit_dry_run_report(
        self,
        report_rows: list[dict],
        stats: dict,
        summary: str,
        *,
        base,
        json_report_path,
        scope: dict,
    ) -> None:
        """Собрать machine-readable JSON dry-run'а и выдать его в файл или stdout.

        Человекочитаемая сводка — сверх JSON, не вместо: при выводе JSON в stdout
        сводка уходит в stderr, чтобы stdout оставался чистым JSON для CAT-14C.
        """
        by_action: dict[str, int] = {}
        by_tool_type: dict[str, dict] = {}
        by_attribute: dict[str, dict] = {}
        for row in report_rows:
            by_action[row["action"]] = by_action.get(row["action"], 0) + 1
            tt = by_tool_type.setdefault(row["tool_type"], {"total": 0, "by_action": {}})
            tt["total"] += 1
            tt["by_action"][row["action"]] = tt["by_action"].get(row["action"], 0) + 1
            at = by_attribute.setdefault(row["attribute"], {"total": 0, "by_action": {}})
            at["total"] += 1
            at["by_action"][row["action"]] = at["by_action"].get(row["action"], 0) + 1

        report = {
            "command": "enrich_attributes",
            "mode": "dry-run",
            "rules_path": str(Path(f"{base}/attribute_rules.json")),
            "generated_at": timezone.now().isoformat(),
            "scope": scope,
            "totals": {
                "processed": stats["processed"],
                "no_attributes": stats["no_attributes"],
                "skipped_priority": stats["skipped_priority"],
                "pruned": sum(stats["pruned"].values()),
                "by_action": by_action,
            },
            "by_tool_type": by_tool_type,
            "by_attribute": by_attribute,
            "rows": report_rows,
        }
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if json_report_path:
            Path(json_report_path).write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(summary))
            self.stdout.write(self.style.SUCCESS(f"dry-run: отчёт записан в {json_report_path}"))
        else:
            self.stderr.write(summary)
            self.stdout.write(payload)

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
        elif av.kind == TEXT:
            pav.value_text = av.text

    @staticmethod
    def _value_changed(pav: ProductAttributeValue, av, option) -> bool:
        """Сравнить фактическое значение сохранённого PAV с извлечённым.

        Сравнение по логическому kind: Decimal для чисел, slug/id для select,
        bool для boolean, str для text. Decimal('10') == Decimal('10.0') —
        одно значение.
        """
        if av.kind == NUMBER:
            return pav.value_decimal != av.number
        if av.kind == SELECT:
            return pav.value_option_id != option.id
        if av.kind == BOOLEAN:
            return pav.value_boolean != av.boolean
        if av.kind == TEXT:
            return pav.value_text != av.text
        return True
