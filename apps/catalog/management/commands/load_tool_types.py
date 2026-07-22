"""Загрузка словаря ``tool_type`` из ``tool_type_rules.json`` (ADR-0001).

``tool_type`` — это АТРИБУТ (вторая ось навигации / SEO-фасет), а не категория.
Создаёт ``Attribute(slug="tool_type")`` и его ``AttributeOption`` (value + slug)
для всех категорий правил. Записи с ``action:"recategorize"`` — это НЕ тип,
варианты для них не создаются. Привязывает ``CategoryAttribute`` (is_filter=True,
is_seo_facet=True) к категориям верхнего уровня, где tool_type применим.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
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
        self._validate_option_slugs(rules)

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

    def _validate_option_slugs(self, rules: ToolTypeRules) -> None:
        """Fail-fast: slug обязан отображаться ровно в одно value; конфликты с БД запрещены.

        Повтор пары (value, slug) в нескольких категориях легален (дедуп по value);
        недопустим slug с >1 distinct value (DEVIATION-2).
        """
        slug_values: dict[str, set[str]] = {}
        for cat in rules.categories:
            for rule in rules.options(cat.category):
                if rule.slug:
                    slug_values.setdefault(rule.slug, set()).add(rule.tool_type)
        ambiguous = {slug: sorted(vals) for slug, vals in slug_values.items() if len(vals) > 1}
        if ambiguous:
            details = "; ".join(f"{slug}: {vals}" for slug, vals in ambiguous.items())
            raise CommandError(f"duplicate option slugs in seed: {details}")

        existing_rows = AttributeOption.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, slug__in=slug_values
        ).values_list("slug", "value")
        db_values: dict[str, list[str]] = {}
        for slug, value in existing_rows:
            db_values.setdefault(slug, []).append(value)
        db_duplicates = {slug: vals for slug, vals in db_values.items() if len(vals) > 1}
        if db_duplicates:
            details = "; ".join(
                f"{slug} x{len(vals)}: {sorted(vals)}" for slug, vals in db_duplicates.items()
            )
            raise CommandError(f"duplicate option slugs in DB: {details}")
        conflicts = {
            slug: (vals[0], next(iter(slug_values[slug])))
            for slug, vals in db_values.items()
            if vals[0] != next(iter(slug_values[slug]))
        }
        if conflicts:
            details = "; ".join(
                f"{slug}: db={db_val!r} vs seed={seed_val!r}"
                for slug, (db_val, seed_val) in conflicts.items()
            )
            raise CommandError(f"option slug conflicts with DB: {details}")

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
