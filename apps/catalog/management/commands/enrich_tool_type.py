"""Извлечение и простановка ``tool_type`` (ADR-0001). Пишет ``EnrichmentLog``.

Алгоритм (раздел 4 задания), для каждого товара:

1. Категория верхнего уровня (Электроинструмент / Ручной инструмент / Оснастка…).
2. ``inherit_1c_subgroup`` → tool_type = подгруппа 1С (лист), результат ``assigned``.
3. ``priority_keyword`` → нормализуем имя (lower, ё=е), идём по правилам по порядку,
   первое совпавшее ключевое слово выигрывает; ``recategorize`` → tool_type не ставим.
   Ничего не совпало → ``moderation``.
4. Каждое решение — строкой в ``EnrichmentLog``.

Обрабатываются товары категорий верхнего уровня, для которых есть правила.
Lookup корневой категории использует явный слой aliases
(``apps.catalog.tool_type_aliases``) — ОДИНАКОВО в ``--dry-run`` и в боевом
прогоне (ENRICH-WRITE-PATH-HARDENING): dry-run-предсказание и то, что реально
пишет боевой прогон, для одного и того же товара совпадают побайтово.

Безопасный режим (``--dry-run``/``--report-only``, ENRICH-DRYRUN-ALIASES):
ничего не пишет в БД, строит machine-readable отчёт matched/moderation/
skipped/conflict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.attrs_cache import flush_attrs_cache_merged
from apps.catalog.ingest import data_dir
from apps.catalog.management.commands.load_tool_types import TOOL_TYPE_SLUG
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Category,
    EnrichmentLog,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductAttributeValue,
)
from apps.catalog.taxonomy_manifest import load_options_index
from apps.catalog.tool_type import ASSIGNED, RECATEGORIZE, ToolTypeRules, normalize
from apps.catalog.tool_type_aliases import AliasConfigError, resolve_live_to_legacy
from apps.catalog.tool_type_subgroup_aliases import (
    SubgroupAliasConfigError,
    known_subgroup_identities,
    resolve_live_subgroup_to_legacy,
)

BATCH = 1000

_REPORT_BUCKETS = ("matched", "moderation", "skipped", "conflict")


@dataclass(frozen=True)
class _PredictedOption:
    """Опция tool_type, предсказанная для отчёта dry-run — НЕ создана в БД."""

    value: str
    slug: str
    sort_order: int = 0


class _DryRunReport:
    """Аккумулятор отчёта ``--dry-run``/``--report-only``.

    Соответствие корзин результату движка: ``matched`` = ``ASSIGNED``,
    ``moderation`` = ``MODERATION``, ``conflict`` = ``RECATEGORIZE`` (товар
    выложен не в тот раздел — движок это и обнаруживает), ``skipped`` —
    корень товара не резолвится ни напрямую, ни через alias (сегодня это
    молчаливый ``continue`` в боевом прогоне).
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {b: 0 for b in _REPORT_BUCKETS}
        self.by_root: dict[str, dict[str, int]] = {}
        self.by_rule_block: dict[str, dict[str, int]] = {}
        self.by_target_slug: dict[str, int] = {}
        self.tool_type_changes: list[dict] = []
        # ENRICH-WRITE-PATH-HARDENING: диагностика inherit_1c_subgroup — лист
        # сайта не резолвится ни напрямую (normalize), ни через subgroup alias.
        # Считается ДОПОЛНИТЕЛЬНО к counts["moderation"] (ex.result у таких
        # товаров всегда MODERATION) — отдельный разрез "почему", не замена.
        self.subgroup_unmapped: dict[str, int] = {}

    def record_subgroup_unmapped(self, leaf_name: str) -> None:
        self.subgroup_unmapped[leaf_name] = self.subgroup_unmapped.get(leaf_name, 0) + 1

    def _bump(self, bucket: str, root: str | None, rule_block: str | None = None) -> None:
        self.counts[bucket] += 1
        row = self.by_root.setdefault(root or "", {b: 0 for b in _REPORT_BUCKETS})
        row[bucket] += 1
        if rule_block is not None:
            block_row = self.by_rule_block.setdefault(rule_block, {b: 0 for b in _REPORT_BUCKETS})
            block_row[bucket] += 1

    def record_skipped(self, root: str | None) -> None:
        self._bump("skipped", root)

    def record_matched(self, root, rule_block, slug, product, old_slug) -> None:
        self._bump("matched", root, rule_block)
        self.by_target_slug[slug] = self.by_target_slug.get(slug, 0) + 1
        if old_slug is not None and old_slug != slug:
            self._record_change(product, old_slug, slug)

    def record_moderation(self, root, rule_block, product, old_slug) -> None:
        self._bump("moderation", root, rule_block)
        if old_slug is not None:
            self._record_change(product, old_slug, None)

    def record_conflict(self, root, rule_block, product, old_slug) -> None:
        self._bump("conflict", root, rule_block)
        if old_slug is not None:
            self._record_change(product, old_slug, None)

    def _record_change(self, product, old_slug, proposed_slug) -> None:
        self.tool_type_changes.append(
            {
                "product_id": product.id,
                "code_1c": product.code_1c or "",
                "old_slug": old_slug,
                "proposed_slug": proposed_slug,
            }
        )

    def to_dict(self, *, filters: dict, aliases_config: dict[str, str]) -> dict:
        return {
            "dry_run": True,
            "filters": filters,
            "aliases_config": aliases_config,
            "counts": self.counts,
            "by_root": self.by_root,
            "by_rule_block": self.by_rule_block,
            "by_target_slug": self.by_target_slug,
            "existing_tool_type_changes": self.tool_type_changes,
            "subgroup_unmapped": self.subgroup_unmapped,
        }


class Command(BaseCommand):
    help = "Проставить tool_type по правилам, записать EnrichmentLog (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с tool_type_rules.json")
        parser.add_argument(
            "--dry-run",
            "--report-only",
            dest="dry_run",
            action="store_true",
            help=(
                "Ничего не писать в БД (PAV/EnrichmentLog/ImportRun): построить "
                "machine-readable отчёт matched/moderation/skipped/conflict."
            ),
        )
        parser.add_argument(
            "--category",
            action="append",
            default=None,
            help="Ограничить прогон live root-категорией (можно повторять).",
        )
        parser.add_argument(
            "--product-ids",
            dest="product_ids",
            default=None,
            help="Явные id товаров через запятую (ограничить прогон).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Максимум товаров для обработки (после фильтров, порядок по id).",
        )
        parser.add_argument(
            "--json-report",
            dest="json_report",
            default=None,
            help="Файл для machine-readable JSON-отчёта dry-run (иначе — stdout).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        base = options["path"] or data_dir()
        rules = ToolTypeRules.from_file(f"{base}/tool_type_rules.json")
        rule_categories = {c.category for c in rules.categories}

        # Валидация aliases — ВСЕГДА, вне зависимости от --dry-run: конфигурационная
        # коллизия обязана останавливать команду ненулевым exit кодом в любом режиме.
        try:
            live_to_legacy = resolve_live_to_legacy(rule_categories)
        except AliasConfigError as exc:
            raise CommandError(f"tool_type_rules aliases: {exc}", returncode=2) from exc

        # Subgroup aliases (ENRICH-WRITE-PATH-HARDENING) — та же валидация ВСЕГДА,
        # по одной на категорию с inherit_1c_subgroup (сегодня — ровно одна).
        subgroup_live_to_legacy: dict[str, dict[str, str]] = {}
        for cat_rules in rules.categories:
            if cat_rules.extraction != "inherit_1c_subgroup":
                continue
            try:
                subgroup_live_to_legacy[cat_rules.category] = resolve_live_subgroup_to_legacy(
                    cat_rules.category, known_subgroup_identities(cat_rules)
                )
            except SubgroupAliasConfigError as exc:
                raise CommandError(
                    f"tool_type_rules subgroup aliases: {exc}", returncode=2
                ) from exc

        attribute = Attribute.objects.filter(slug=TOOL_TYPE_SLUG).first()
        if attribute is None:
            self.stderr.write("Атрибут tool_type не найден — выполните load_tool_types.")
            return ""

        top_name_by_id, path_str_by_id = self._category_meta()
        opt_by_slug, opt_by_value = self._option_indexes(attribute)
        # Wave 7.1/H1: runtime-создание AttributeOption — только из canonical
        # taxonomy manifest (см. _resolve_option); extraction не меняется.
        manifest_options = load_options_index()
        # Существующие PAV — объектами (для bulk_update при повторном прогоне).
        # Иначе update_or_create по одной строке вешает Postgres (≈16k round-trip'ов
        # + шторм сигналов rebuild_attrs_cache).
        existing_pav = {
            pav.product_id: pav for pav in ProductAttributeValue.objects.filter(attribute=attribute)
        }

        product_ids = self._parse_product_ids(options.get("product_ids"))
        category_names = options.get("category")
        category_filter_ids = None
        if category_names:
            category_filter_ids = self._category_ids_for_names(category_names, top_name_by_id)

        # Фильтры — нейтральны без флагов: qs совпадает с прежним запросом байт-в-байт,
        # если ни один из --product-ids/--category/--limit не передан.
        qs = Product.objects.exclude(category__isnull=True).select_related("category")
        if product_ids is not None:
            qs = qs.filter(id__in=product_ids)
        if category_filter_ids is not None:
            qs = qs.filter(category_id__in=category_filter_ids)
        if options.get("limit") is not None:
            qs = qs.order_by("id")[: options["limit"]]
        qs = qs.iterator(chunk_size=2000)

        if dry_run:
            return self._handle_dry_run(
                qs,
                rules=rules,
                rule_categories=rule_categories,
                live_to_legacy=live_to_legacy,
                subgroup_live_to_legacy=subgroup_live_to_legacy,
                top_name_by_id=top_name_by_id,
                opt_by_slug=opt_by_slug,
                opt_by_value=opt_by_value,
                manifest_options=manifest_options,
                existing_pav=existing_pav,
                filters={
                    "category": category_names,
                    "product_ids": product_ids,
                    "limit": options.get("limit"),
                },
                json_report_path=options.get("json_report"),
            )

        return self._handle_write(
            qs,
            rules=rules,
            rule_categories=rule_categories,
            live_to_legacy=live_to_legacy,
            subgroup_live_to_legacy=subgroup_live_to_legacy,
            top_name_by_id=top_name_by_id,
            path_str_by_id=path_str_by_id,
            attribute=attribute,
            opt_by_slug=opt_by_slug,
            opt_by_value=opt_by_value,
            manifest_options=manifest_options,
            existing_pav=existing_pav,
        )

    # --- боевой (пишущий) прогон ------------------------------------------

    def _handle_write(
        self,
        qs,
        *,
        rules,
        rule_categories,
        live_to_legacy,
        subgroup_live_to_legacy,
        top_name_by_id,
        path_str_by_id,
        attribute,
        opt_by_slug,
        opt_by_value,
        manifest_options,
        existing_pav,
    ):
        run = ImportRun.objects.create(source="enrich_tool_type")
        stats = {
            "processed": 0,
            "tool_type_assigned": 0,
            "moderation": 0,
            "recategorize_flagged": 0,
        }

        logs: list[EnrichmentLog] = []
        pav_create: list[ProductAttributeValue] = []
        pav_update: list[ProductAttributeValue] = []
        pav_delete_ids: list[int] = []
        cache_updates: list[Product] = []

        try:
            with transaction.atomic():
                for product in qs:
                    cat = product.category
                    top_name = top_name_by_id.get(cat.id)
                    # Тот же live_to_legacy слой, что и в _handle_dry_run (ENRICH-
                    # WRITE-PATH-HARDENING): для 10 из 13 блоков без alias — байт-в-
                    # байт прежнее поведение (top_name уже совпадает с legacy).
                    # Для 3 алиасированных корней (Спецодежда, Строительное, Оснастка)
                    # боевой прогон теперь официально ведёт себя как dry-run-предсказание.
                    legacy_category = (
                        top_name if top_name in rule_categories else live_to_legacy.get(top_name)
                    )
                    if legacy_category is None:
                        continue

                    sub_name, _unmapped = self._translate_subgroup(
                        rules, legacy_category, cat.name, subgroup_live_to_legacy
                    )
                    ex = rules.extract(
                        legacy_category, product.original_name or product.name, sub_name
                    )
                    stats["processed"] += 1

                    tool_type_value = ""
                    if ex.result == ASSIGNED:
                        option = self._resolve_option(
                            attribute, ex, opt_by_slug, opt_by_value, manifest_options
                        )
                        tool_type_value = option.value
                        stats["tool_type_assigned"] += 1
                        pav = existing_pav.get(product.id)
                        if pav is None:
                            pav_create.append(
                                ProductAttributeValue(
                                    product=product, attribute=attribute, value_option=option
                                )
                            )
                        elif pav.value_option_id != option.id:
                            pav.value_option = option
                            pav_update.append(pav)
                        product.attrs_cache = {
                            **(product.attrs_cache or {}),
                            "tool_type": option.value,
                        }
                        cache_updates.append(product)
                    elif ex.result == RECATEGORIZE:
                        stats["recategorize_flagged"] += 1
                        self._prune_tool_type(product, existing_pav, pav_delete_ids, cache_updates)
                    else:
                        stats["moderation"] += 1
                        self._prune_tool_type(product, existing_pav, pav_delete_ids, cache_updates)

                    logs.append(
                        EnrichmentLog(
                            run=run,
                            product_external_id=product.code_1c or "",
                            raw_name=(product.original_name or product.name)[:512],
                            result=ex.result,
                            tool_type=tool_type_value or ex.tool_type,
                            matched_keyword=ex.matched_keyword,
                            category_path=path_str_by_id.get(cat.id, cat.name)[:512],
                        )
                    )

                    if len(logs) >= BATCH:
                        EnrichmentLog.objects.bulk_create(logs, batch_size=BATCH)
                        logs.clear()
                    if len(pav_create) >= BATCH:
                        ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                        pav_create.clear()
                    if len(pav_update) >= BATCH:
                        ProductAttributeValue.objects.bulk_update(
                            pav_update, ["value_option"], batch_size=BATCH
                        )
                        pav_update.clear()
                    if len(cache_updates) >= BATCH:
                        flush_attrs_cache_merged(
                            cache_updates, lambda _p: {TOOL_TYPE_SLUG}, batch_size=BATCH
                        )
                        cache_updates.clear()
                    if len(pav_delete_ids) >= BATCH:
                        ProductAttributeValue.objects.filter(id__in=pav_delete_ids).delete()
                        pav_delete_ids.clear()

                if logs:
                    EnrichmentLog.objects.bulk_create(logs, batch_size=BATCH)
                if pav_create:
                    ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                if pav_update:
                    ProductAttributeValue.objects.bulk_update(
                        pav_update, ["value_option"], batch_size=BATCH
                    )
                if cache_updates:
                    flush_attrs_cache_merged(
                        cache_updates, lambda _p: {TOOL_TYPE_SLUG}, batch_size=BATCH
                    )
                if pav_delete_ids:
                    ProductAttributeValue.objects.filter(id__in=pav_delete_ids).delete()

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
                f"Обогащение: обработано {stats['processed']}, "
                f"tool_type проставлен {stats['tool_type_assigned']}, "
                f"модерация {stats['moderation']}, recategorize {stats['recategorize_flagged']}."
            )
        )
        return str(run.pk)

    # --- безопасный режим --------------------------------------------------

    def _handle_dry_run(
        self,
        qs,
        *,
        rules,
        rule_categories,
        live_to_legacy,
        subgroup_live_to_legacy,
        top_name_by_id,
        opt_by_slug,
        opt_by_value,
        manifest_options,
        existing_pav,
        filters,
        json_report_path,
    ) -> str:
        report = _DryRunReport()

        for product in qs:
            cat = product.category
            top_name = top_name_by_id.get(cat.id)
            legacy_category = (
                top_name if top_name in rule_categories else live_to_legacy.get(top_name)
            )
            if legacy_category is None:
                report.record_skipped(top_name)
                continue

            sub_name, unmapped = self._translate_subgroup(
                rules, legacy_category, cat.name, subgroup_live_to_legacy
            )
            ex = rules.extract(legacy_category, product.original_name or product.name, sub_name)
            old_slug = self._existing_slug(existing_pav.get(product.id))

            if ex.result == ASSIGNED:
                predicted = self._resolve_option(
                    None,
                    ex,
                    opt_by_slug,
                    opt_by_value,
                    manifest_options,
                    persist=False,
                )
                report.record_matched(top_name, legacy_category, predicted.slug, product, old_slug)
            elif ex.result == RECATEGORIZE:
                report.record_conflict(top_name, legacy_category, product, old_slug)
            else:
                report.record_moderation(top_name, legacy_category, product, old_slug)
            if unmapped:
                report.record_subgroup_unmapped(cat.name)

        payload = json.dumps(
            report.to_dict(filters=filters, aliases_config=live_to_legacy),
            ensure_ascii=False,
            indent=2,
        )
        if json_report_path:
            Path(json_report_path).write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"dry-run: отчёт записан в {json_report_path}"))
        else:
            self.stdout.write(payload)
        return payload

    @staticmethod
    def _translate_subgroup(
        rules: ToolTypeRules,
        legacy_category: str,
        leaf_name: str,
        subgroup_live_to_legacy: dict[str, dict[str, str]],
    ) -> tuple[str, bool]:
        """Подгруппа для ``rules.extract`` (ENRICH-WRITE-PATH-HARDENING).

        Лист сайта (``leaf_name`` = ``cat.name``), уже резолвящийся напрямую
        (совпадает через ``normalize`` с override-подгруппой или базовым типом
        ``inherit_1c_subgroup``-блока) — без изменений. Иначе — перевод через
        ``tool_type_subgroup_aliases`` для подтверждённых случаев. Возвращает
        ``(effective_subgroup, unmapped)`` — ``unmapped=True``, когда ни то,
        ни другое не сработало (движок безопасно вернёт MODERATION, а не
        сырое значение листа — см. ``tool_type.py::extract``)."""
        cat_rules = rules.get(legacy_category)
        if cat_rules is None or cat_rules.extraction != "inherit_1c_subgroup":
            return leaf_name, False
        known = known_subgroup_identities(cat_rules)
        if normalize(leaf_name) in {normalize(identity) for identity in known}:
            return leaf_name, False
        mapped = subgroup_live_to_legacy.get(legacy_category, {}).get(leaf_name)
        if mapped is not None:
            return mapped, False
        return leaf_name, True

    @staticmethod
    def _existing_slug(pav: ProductAttributeValue | None) -> str | None:
        if pav is None:
            return None
        opt = pav.value_option
        return opt.slug or normalize(opt.value)

    # --- индексы и хелперы -----------------------------------------------

    @staticmethod
    def _parse_product_ids(raw: str | None) -> list[int] | None:
        if raw is None:
            return None
        try:
            return [int(chunk) for chunk in raw.replace(",", " ").split()]
        except ValueError as exc:
            raise CommandError(f"--product-ids: ожидались целые id: {raw!r}", returncode=2) from exc

    @staticmethod
    def _category_ids_for_names(names: list[str], top_name_by_id: dict[int, str]) -> list[int]:
        wanted = set(names)
        unknown = wanted - set(top_name_by_id.values())
        if unknown:
            raise CommandError(
                f"--category: неизвестные live root категории: {sorted(unknown)}", returncode=2
            )
        return [cid for cid, name in top_name_by_id.items() if name in wanted]

    @staticmethod
    def _category_meta() -> tuple[dict[int, str], dict[int, str]]:
        """Один проход по дереву: id категории → (имя верхнего уровня, полный путь).

        treebeard кодирует предков префиксами ``path`` кратными ``steplen`` —
        путь строим без запросов на каждый товар.
        """
        cats = list(Category.objects.all())
        name_by_path = {c.path: c.name for c in cats}
        step = Category.steplen
        top_name: dict[int, str] = {}
        path_str: dict[int, str] = {}
        for c in cats:
            chain = [name_by_path.get(c.path[: step * i], "") for i in range(1, c.depth + 1)]
            chain = [n for n in chain if n]
            top_name[c.id] = chain[0] if chain else c.name
            path_str[c.id] = " / ".join(chain) if chain else c.name
        return top_name, path_str

    @staticmethod
    def _option_indexes(attribute: Attribute):
        opt_by_slug: dict[str, AttributeOption] = {}
        opt_by_value: dict[str, AttributeOption] = {}
        for opt in attribute.options.all():
            if opt.slug:
                opt_by_slug[opt.slug] = opt
            opt_by_value[normalize(opt.value)] = opt
        return opt_by_slug, opt_by_value

    @staticmethod
    def _prune_tool_type(product, existing_pav, pav_delete_ids, cache_updates) -> None:
        """Снять устаревший tool_type у товара, переставшего быть assigned (стал
        recategorize/moderation): удалить PAV и убрать ключ из attrs_cache. Иначе
        товар остаётся в старом фасете (напр. садовая техника в «Аккумуляторах»)."""
        pav = existing_pav.get(product.id)
        if pav is not None:
            pav_delete_ids.append(pav.id)
        if product.attrs_cache and "tool_type" in product.attrs_cache:
            product.attrs_cache = {k: v for k, v in product.attrs_cache.items() if k != "tool_type"}
            cache_updates.append(product)

    def _resolve_option(
        self,
        attribute,
        ex,
        opt_by_slug,
        opt_by_value,
        manifest_options,
        *,
        persist: bool = True,
    ) -> AttributeOption | _PredictedOption:
        """Опция tool_type для assigned.

        Wave 7.1/H1 guard: создание options — только из canonical taxonomy
        manifest (taxonomy не растёт в runtime). Значение вне manifest —
        fail-closed CommandError. Extraction-логика не меняется.

        ``persist=False`` (ENRICH-DRYRUN-ALIASES): для отчёта dry-run — вернуть
        предсказанную опцию (value/slug) БЕЗ записи в БД, даже если её ещё нет
        среди существующих options.
        """
        if ex.slug and ex.slug in opt_by_slug:
            return opt_by_slug[ex.slug]
        key = normalize(ex.tool_type)
        if key in opt_by_value:
            return opt_by_value[key]
        mopt = manifest_options.by_slug(ex.slug) if ex.slug else None
        if mopt is None:
            mopt = manifest_options.by_normalized_value(ex.tool_type)
        if mopt is None:
            raise CommandError(
                f"option_not_in_manifest: {ex.tool_type!r} (slug={ex.slug!r}). "
                "Taxonomy не растёт в runtime: добавьте option в canonical "
                "taxonomy manifest и выполните seed (load_tool_types)."
            )
        if not persist:
            return _PredictedOption(value=mopt.value, slug=mopt.slug, sort_order=mopt.sort_order)
        option = AttributeOption.objects.create(
            attribute=attribute, value=mopt.value, slug=mopt.slug, sort_order=mopt.sort_order
        )
        opt_by_value[key] = option
        if option.slug:
            opt_by_slug[option.slug] = option
        return option
