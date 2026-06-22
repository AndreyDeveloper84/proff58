"""Загрузка словаря характеристик из ``attribute_rules.json`` (Фаза B, #96).

Создаёт схему EAV по канону движка #99 (`data/attribute_rules.json`):
``Attribute`` (тип/единица/is_ai_feature), ``AttributeOption`` для select-характеристик
и привязку ``CategoryAttribute`` (is_filter/is_seo_facet) к категории верхнего уровня
из поля ``category`` блока tool_type.

Идемпотентна: существующий ``Attribute`` НЕ пересоздаётся — обновляются только
безопасные поля (``unit``/``is_filterable``/``is_ai_feature``); ручные правки имени/типа
не затираются. Сам движок извлечения (`attribute_extract.py`) тут не используется —
это загрузчик схемы, а не экстрактор.
"""

from __future__ import annotations

import json
from pathlib import Path

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

# kind словаря → тип атрибута модели. number храним как DECIMAL (value_decimal).
KIND_TO_TYPE = {
    "select": AttributeType.SELECT,
    "number": AttributeType.DECIMAL,
    "boolean": AttributeType.BOOLEAN,
}

# Безопасные для перезаписи поля Attribute (имя/тип/slug не трогаем у существующих).
SAFE_FIELDS = ("unit", "is_filterable", "is_ai_feature")


class Command(BaseCommand):
    help = "Создать Attribute/AttributeOption/CategoryAttribute из data/attribute_rules.json."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        data = json.loads(Path(f"{base}/attribute_rules.json").read_text(encoding="utf-8"))

        attrs, opts, bound = 0, 0, 0
        with transaction.atomic():
            for tt in data.get("tool_types", []):
                category_name = tt.get("category")
                for a in tt.get("attributes", []):
                    attribute, opt_count = self._load_attribute(a)
                    attrs += 1
                    opts += opt_count
                    if category_name and self._bind_category(attribute, a, category_name):
                        bound += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Характеристики готовы. Атрибутов: {attrs}, вариантов: {opts}, "
                f"привязок к категориям: {bound}."
            )
        )
        return str(attrs)

    def _load_attribute(self, a: dict) -> tuple[Attribute, int]:
        attribute, created = Attribute.objects.get_or_create(
            slug=a["slug"],
            defaults=dict(
                name=a["name"],
                attribute_type=KIND_TO_TYPE.get(a["kind"], AttributeType.TEXT),
                unit=a.get("unit", ""),
                is_filterable=a.get("is_filter", True),
                is_ai_feature=a.get("is_ai_feature", False),
            ),
        )
        if not created:
            # Существующий атрибут: обновляем только безопасные поля, не пересоздаём.
            new_values = {
                "unit": a.get("unit", ""),
                "is_filterable": a.get("is_filter", True),
                "is_ai_feature": a.get("is_ai_feature", False),
            }
            changed = [f for f in SAFE_FIELDS if getattr(attribute, f) != new_values[f]]
            if changed:
                for f in changed:
                    setattr(attribute, f, new_values[f])
                attribute.save(update_fields=changed)

        opt_count = 0
        if a["kind"] == "select":
            for sort, opt in enumerate(a.get("options", [])):
                AttributeOption.objects.update_or_create(
                    attribute=attribute,
                    value=opt["value"],
                    defaults=dict(slug=opt.get("slug", ""), sort_order=sort),
                )
                opt_count += 1
        return attribute, opt_count

    def _bind_category(self, attribute: Attribute, a: dict, category_name: str) -> bool:
        # Депт-1 (топ) имеет приоритет — обратная совместимость; если топа с таким
        # именем нет, а имя уникально в дереве — биндим к точной под-категории
        # (напр. «Алмазные круги»), чтобы фасет не засорял всю топ-категорию.
        qs = Category.objects.filter(name=category_name)
        category = qs.filter(depth=1).first() or (qs.first() if qs.count() == 1 else None)
        if category is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  категория «{category_name}» не найдена или неоднозначна — "
                    f"сначала выполните build_categories."
                )
            )
            return False
        CategoryAttribute.objects.update_or_create(
            category=category,
            attribute=attribute,
            defaults=dict(
                is_filter=a.get("is_filter", True),
                is_seo_facet=a.get("is_seo_facet", False),
            ),
        )
        return True
