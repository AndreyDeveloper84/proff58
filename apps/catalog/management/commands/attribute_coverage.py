"""Аналитика покрытия характеристик: какой % товаров tool_type матчит каждый атрибут.

Read-only — ничего не пишет в БД. Нужна ДО включения характеристики в обогащение
(issue #96): если `voltage` встречается у 93% названий, а `torque` — у 12%, то
torque пока рано внедрять. По результату слабые атрибуты убираются прямо из
``data/attribute_rules.json`` (данные, не код).

    ./manage.py attribute_coverage --tool-type dreli-shurupoverty
    ./manage.py attribute_coverage --tool-type dreli-shurupoverty --examples 10
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.models import Product

DEFAULT_RULES = "data/attribute_rules.json"
TOOL_TYPE_ATTR = "tool_type"


class Command(BaseCommand):
    help = "Покрытие характеристик по названиям товаров выбранного tool_type (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--tool-type", default="dreli-shurupoverty")
        parser.add_argument("--rules", default=DEFAULT_RULES)
        parser.add_argument(
            "--examples",
            type=int,
            default=0,
            help="Показать N примеров названий без матча по каждому атрибуту.",
        )

    def handle(self, *args, **opts):
        rules_path = Path(opts["rules"])
        if not rules_path.is_absolute():
            rules_path = Path(settings.BASE_DIR) / rules_path
        rules = AttributeRules.from_file(rules_path)

        tt = opts["tool_type"]
        attr_rules = rules.rules_for(tt)
        if not attr_rules:
            self.stderr.write(self.style.ERROR(f"Нет правил для tool_type={tt} в {rules_path}"))
            return

        qs = (
            Product.objects.filter(
                attribute_values__attribute__slug=TOOL_TYPE_ATTR,
                attribute_values__value_option__slug=tt,
            )
            .distinct()
            .values_list("original_name", "name")
            .iterator(chunk_size=2000)
        )

        total = 0
        matched: dict[str, int] = {r.slug: 0 for r in attr_rules}
        samples: dict[str, Counter] = {r.slug: Counter() for r in attr_rules}
        misses: dict[str, list[str]] = {r.slug: [] for r in attr_rules}
        n_examples = opts["examples"]

        for original_name, name in qs:
            total += 1
            text = original_name or name or ""
            found = {v.slug: v for v in rules.extract(tt, text)}
            for r in attr_rules:
                value = found.get(r.slug)
                if value is not None:
                    matched[r.slug] += 1
                    samples[r.slug][_sample(value)] += 1
                elif n_examples and len(misses[r.slug]) < n_examples:
                    misses[r.slug].append(text)

        if total == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Товаров с tool_type={tt} не найдено — сначала импорт и enrich_tool_type."
                )
            )
            return

        self.stdout.write(f"\ntool_type = {tt}: товаров {total}\n")
        self.stdout.write(f"{'атрибут':20} {'покрытие':>14}   топ-значения")
        for r in attr_rules:
            pct = matched[r.slug] * 100 // total
            top = ", ".join(f"{val}×{cnt}" for val, cnt in samples[r.slug].most_common(4))
            self.stdout.write(f"{r.slug:20} {matched[r.slug]:>6}/{total} {pct:>3}%   {top}")
            for ex in misses[r.slug]:
                self.stdout.write(f"    нет матча: {ex}")


def _sample(value) -> str:
    if value.option_value:
        return value.option_value
    if value.number is not None:
        return f"{value.number}{value.unit}"
    return "да" if value.boolean else "нет"
