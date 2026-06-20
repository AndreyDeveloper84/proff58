"""Аналитика покрытия характеристик ДО enrichment (Шаг 1 плана, #96).

Read-only: ничего не пишет в БД. Прогоняет правила ``attribute_rules.json`` по
названиям товаров и показывает, какой % товаров каждого tool_type имеет
извлекаемое значение по каждому атрибуту. Это драйвер решения: что делать
фильтром, что SEO-фасетом, а что метить ``is_ai_feature`` (низкое покрытие
regex → добор LLM позже). Запуск до записи данных бережёт каталог от мусора.
"""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir
from apps.catalog.models import Product

TOOL_TYPE_SLUG = "tool_type"


class Command(BaseCommand):
    help = "Отчёт покрытия характеристик по товарам (read-only, до enrichment)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")
        parser.add_argument(
            "--tool-type",
            default=None,
            help="Ограничить одним tool_type (значение или slug). По умолчанию — все.",
        )

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules = AttributeRules.from_file(f"{base}/attribute_rules.json")

        wanted = options["tool_type"]
        totals: dict[str, int] = defaultdict(int)
        found: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        qs = Product.objects.exclude(category__isnull=True).only(
            "attrs_cache", "original_name", "name"
        )
        for product in qs.iterator(chunk_size=2000):
            tool_type = (product.attrs_cache or {}).get(TOOL_TYPE_SLUG)
            if not tool_type:
                continue
            item = rules.get(tool_type)
            if item is None:
                continue
            if wanted and wanted not in (item.tool_type, item.slug):
                continue

            totals[item.tool_type] += 1
            name = product.original_name or product.name
            for ev in rules.extract_all(tool_type, name):
                found[item.tool_type][ev.spec.slug] += 1

        if not totals:
            self.stdout.write(self.style.WARNING("Нет товаров с подходящим tool_type."))
            return ""

        for item in rules.tool_types:
            n = totals.get(item.tool_type, 0)
            if not n:
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"{item.tool_type} (N={n})"))
            for spec in item.attributes:
                cnt = found[item.tool_type].get(spec.slug, 0)
                pct = round(100 * cnt / n)
                ai = " [ai-feature]" if spec.is_ai_feature else ""
                self.stdout.write(f"  {spec.slug:18} найдено {pct:3d}%  ({cnt}/{n}){ai}")
        return ""
