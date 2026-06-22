"""Извлечение и простановка ``tool_type`` (ADR-0001). Пишет ``EnrichmentLog``.

Алгоритм (раздел 4 задания), для каждого товара:

1. Категория верхнего уровня (Электроинструмент / Ручной инструмент / Оснастка…).
2. ``inherit_1c_subgroup`` → tool_type = подгруппа 1С (лист), результат ``assigned``.
3. ``priority_keyword`` → нормализуем имя (lower, ё=е), идём по правилам по порядку,
   первое совпавшее ключевое слово выигрывает; ``recategorize`` → tool_type не ставим.
   Ничего не совпало → ``moderation``.
4. Каждое решение — строкой в ``EnrichmentLog``.

Обрабатываются товары категорий верхнего уровня, для которых есть правила.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

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
from apps.catalog.tool_type import ASSIGNED, RECATEGORIZE, ToolTypeRules, normalize, transliterate

BATCH = 1000


class Command(BaseCommand):
    help = "Проставить tool_type по правилам, записать EnrichmentLog (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с tool_type_rules.json")

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules = ToolTypeRules.from_file(f"{base}/tool_type_rules.json")
        rule_categories = {c.category for c in rules.categories}

        attribute = Attribute.objects.filter(slug=TOOL_TYPE_SLUG).first()
        if attribute is None:
            self.stderr.write("Атрибут tool_type не найден — выполните load_tool_types.")
            return ""

        top_name_by_id, path_str_by_id = self._category_meta()
        opt_by_slug, opt_by_value = self._option_indexes(attribute)
        # Существующие PAV — объектами (для bulk_update при повторном прогоне).
        # Иначе update_or_create по одной строке вешает Postgres (≈16k round-trip'ов
        # + шторм сигналов rebuild_attrs_cache).
        existing_pav = {
            pav.product_id: pav for pav in ProductAttributeValue.objects.filter(attribute=attribute)
        }

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
        cache_updates: list[Product] = []

        qs = (
            Product.objects.exclude(category__isnull=True)
            .select_related("category")
            .iterator(chunk_size=2000)
        )
        try:
            with transaction.atomic():
                for product in qs:
                    cat = product.category
                    top_name = top_name_by_id.get(cat.id)
                    if top_name not in rule_categories:
                        continue

                    ex = rules.extract(top_name, product.original_name or product.name, cat.name)
                    stats["processed"] += 1

                    tool_type_value = ""
                    if ex.result == ASSIGNED:
                        option = self._resolve_option(attribute, ex, opt_by_slug, opt_by_value)
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
                    else:
                        stats["moderation"] += 1

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
                        Product.objects.bulk_update(
                            cache_updates, ["attrs_cache"], batch_size=BATCH
                        )
                        cache_updates.clear()

                if logs:
                    EnrichmentLog.objects.bulk_create(logs, batch_size=BATCH)
                if pav_create:
                    ProductAttributeValue.objects.bulk_create(pav_create, batch_size=BATCH)
                if pav_update:
                    ProductAttributeValue.objects.bulk_update(
                        pav_update, ["value_option"], batch_size=BATCH
                    )
                if cache_updates:
                    Product.objects.bulk_update(cache_updates, ["attrs_cache"], batch_size=BATCH)

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

    # --- индексы и хелперы -----------------------------------------------

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

    def _resolve_option(self, attribute, ex, opt_by_slug, opt_by_value) -> AttributeOption:
        """Опция tool_type для assigned. Для inherit-подгрупп вне правил — создаём."""
        if ex.slug and ex.slug in opt_by_slug:
            return opt_by_slug[ex.slug]
        key = normalize(ex.tool_type)
        if key in opt_by_value:
            return opt_by_value[key]
        slug = ex.slug or self._unique_option_slug(attribute, ex.tool_type)
        option = AttributeOption.objects.create(
            attribute=attribute, value=ex.tool_type, slug=slug, sort_order=900
        )
        opt_by_value[key] = option
        if slug:
            opt_by_slug[slug] = option
        return option

    @staticmethod
    def _unique_option_slug(attribute: Attribute, value: str) -> str:
        # Транслитерируем кириллицу до slugify: иначе slugify(allow_unicode=False)
        # вырезает её в пустоту → бессмысленные tip-N. «Прочая оснастка» →
        # prochaya-osnastka. Фолбэк tip — только для совсем пустого результата.
        base = slugify(transliterate(value), allow_unicode=False) or "tip"
        slug = base
        n = 2
        taken = set(attribute.options.values_list("slug", flat=True))
        while slug in taken:
            slug = f"{base}-{n}"
            n += 1
        return slug
