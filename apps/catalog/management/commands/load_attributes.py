"""Загрузка словаря характеристик из ``attribute_rules.json`` (Фаза B, #96).

Создаёт ``Attribute`` (тип/единица/is_ai_feature), ``AttributeOption`` для
select-характеристик и привязывает ``CategoryAttribute`` (is_filter/is_seo_facet/
filter_kind) к категории верхнего уровня. Идемпотентно (update_or_create).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.attribute_extract import KIND_SELECT, AttributeRules, AttributeSpec
from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Category,
    CategoryAttribute,
)


class Command(BaseCommand):
    help = "Создать Attribute/AttributeOption/CategoryAttribute из data/attribute_rules.json."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules = AttributeRules.from_file(f"{base}/attribute_rules.json")

        attrs_created = 0
        options_created = 0
        with transaction.atomic():
            for tt in rules.tool_types:
                for spec in tt.attributes:
                    created, opts = self._load_attribute(spec, tt.category)
                    attrs_created += int(created)
                    options_created += opts

        self.stdout.write(
            self.style.SUCCESS(
                f"Характеристики готовы. Создано атрибутов: {attrs_created}, "
                f"вариантов: {options_created}."
            )
        )
        return str(attrs_created)

    def _load_attribute(self, spec: AttributeSpec, category_name: str) -> tuple[bool, int]:
        attribute, created = Attribute.objects.update_or_create(
            slug=spec.slug,
            defaults=dict(
                name=spec.name,
                attribute_type=spec.attribute_type,
                unit=spec.unit,
                is_filterable=spec.is_filter,
                is_ai_feature=spec.is_ai_feature,
            ),
        )

        options_created = 0
        if spec.kind == KIND_SELECT:
            for sort, opt in enumerate(spec.options):
                _, opt_created = AttributeOption.objects.update_or_create(
                    attribute=attribute,
                    value=opt.value,
                    defaults=dict(slug=opt.slug, sort_order=sort),
                )
                options_created += int(opt_created)

        self._bind_category(attribute, spec, category_name)
        return created, options_created

    def _bind_category(
        self, attribute: Attribute, spec: AttributeSpec, category_name: str
    ) -> None:
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
            defaults=dict(
                is_filter=spec.is_filter,
                is_seo_facet=spec.is_seo_facet,
                filter_kind=spec.filter_kind,
            ),
        )
