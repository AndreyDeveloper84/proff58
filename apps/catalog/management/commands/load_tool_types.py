"""Загрузка словаря ``tool_type`` из ``tool_type_rules.json`` (ADR-0001).

``tool_type`` — это АТРИБУТ (вторая ось навигации / SEO-фасет), а не категория.
Создаёт ``Attribute(slug="tool_type")`` и его ``AttributeOption`` (value + slug)
для всех категорий правил. Записи с ``action:"recategorize"`` — это НЕ тип,
варианты для них не создаются. Привязывает ``CategoryAttribute`` (is_filter=True,
is_seo_facet=True) к категориям верхнего уровня, где tool_type применим.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
)
from apps.catalog.tool_type import ToolTypeRules

TOOL_TYPE_SLUG = "tool_type"
TOOL_TYPE_NAME = "Тип инструмента"


class Command(BaseCommand):
    help = "Создать Attribute(tool_type) и его варианты из data/tool_type_rules.json."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с tool_type_rules.json")

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules = ToolTypeRules.from_file(f"{base}/tool_type_rules.json")

        with transaction.atomic():
            attribute, _ = Attribute.objects.get_or_create(
                slug=TOOL_TYPE_SLUG,
                defaults=dict(
                    name=TOOL_TYPE_NAME,
                    attribute_type=AttributeType.SELECT,
                    is_filterable=True,
                    is_comparable=False,
                ),
            )

            options_created = 0
            per_category: dict[str, int] = {}
            for cat in rules.categories:
                count = 0
                for sort, rule in enumerate(rules.options(cat.category)):
                    _, created = AttributeOption.objects.update_or_create(
                        attribute=attribute,
                        value=rule.tool_type,
                        defaults=dict(slug=rule.slug, sort_order=sort),
                    )
                    options_created += int(created)
                    count += 1
                per_category[cat.category] = count
                self._bind_category(attribute, cat.category)

        summary = ", ".join(f"{name}: {n}" for name, n in per_category.items())
        self.stdout.write(
            self.style.SUCCESS(
                f"Атрибут tool_type готов. Вариантов создано: {options_created}. "
                f"По категориям — {summary}."
            )
        )
        return str(options_created)

    def _bind_category(self, attribute: Attribute, category_name: str) -> None:
        """Привязать tool_type к категории верхнего уровня (если она есть в дереве)."""
        top = Category.objects.filter(depth=1, name=category_name).first()
        if top is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  категория верхнего уровня «{category_name}» не найдена — "
                    f"сначала выполните build_categories."
                )
            )
            return
        CategoryAttribute.objects.update_or_create(
            category=top,
            attribute=attribute,
            defaults=dict(is_filter=True, is_seo_facet=True),
        )
