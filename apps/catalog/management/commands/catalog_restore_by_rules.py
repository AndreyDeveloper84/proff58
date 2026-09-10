"""Достройка обрезанных названий по правилам, а не по одному поиску на позицию.

1С обрезала 6 164 наименования по 50 символов. Часть из них восстановилась по
донорам (`catalog_name_analogs`) и по карточкам производителя, но 5 281 позиция
осталась, и искать каждую вручную нереально. Зато названия внутри категории
однотипны: у всех метрических плашек хвост «ГОСТ 9740-71», у свёрл средней
серии — «сталь Р6М5, ГОСТ 10902».

Такие закономерности описаны регулярками в ``data/name_restore_rules.json``.
Каждое правило выведено из полных названий той же серии в каталоге либо из
карточки производителя — обоснование лежит рядом, в поле ``note``.

Команда трогает только позиции, у которых:

* строка 1С обрезана (ровно 50 символов) — остальные не пострадали;
* имя ещё не восстановлено из другого источника — найденное в карточке
  производителя правило не перезаписывает.

Порядок:

    catalog_restore_by_rules --dry-run --limit 20    # посмотреть, что выйдет
    catalog_restore_by_rules --rule plashka-m-gost9740 --dry-run
    catalog_restore_by_rules --commit
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog import provenance
from apps.catalog.models import Product

CUT_LENGTH = 50
RULES_PATH = Path(settings.BASE_DIR) / "data" / "name_restore_rules.json"


class Command(BaseCommand):
    help = "Достроить обрезанные названия по правилам из data/name_restore_rules.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit", action="store_true", help="Записать (по умолчанию dry-run)."
        )
        parser.add_argument("--rule", help="Применить только правило с этим id.")
        parser.add_argument("--category", help="Только товары этой категории сайта.")
        parser.add_argument("--limit", type=int, default=10, help="Сколько примеров показать.")

    def handle(self, *args, **options):
        rules = self._load(options.get("rule"))
        queryset = Product.objects.only(
            "id", "name", "original_name", "article", "content_field_sources"
        ).order_by("id")
        if options.get("category"):
            queryset = queryset.filter(category__name=options["category"])

        stats: dict[str, int] = {}
        shown = 0
        applied_total = 0
        for product in queryset.iterator(chunk_size=1000):
            if len(product.original_name or "") != CUT_LENGTH:
                continue
            if (product.content_field_sources or {}).get("name"):
                continue  # имя уже восстановлено — правило поверх не кладём

            match = self._first_match(rules, product.name)
            if match is None:
                continue
            rule, restored = match
            if restored == product.name:
                continue

            stats[rule["id"]] = stats.get(rule["id"], 0) + 1
            if shown < options["limit"]:
                shown += 1
                self.stdout.write(f"  было:  {product.name}")
                self.stdout.write(self.style.SUCCESS(f"  стало: {restored}"))
                self.stdout.write(f"  правило: {rule['id']}\n")

            if options["commit"]:
                applied_total += self._apply(product, restored, rule)

        self.stdout.write("")
        for rule_id, count in sorted(stats.items(), key=lambda pair: -pair[1]):
            self.stdout.write(f"{rule_id:<34} {count}")
        self.stdout.write(self.style.SUCCESS(f"\nвсего подходит: {sum(stats.values())}"))
        if options["commit"]:
            self.stdout.write(self.style.SUCCESS(f"записано: {applied_total}"))
        else:
            self.stdout.write(self.style.WARNING("--dry-run: в базу ничего не записано."))

    def _load(self, only: str | None) -> list[dict]:
        if not RULES_PATH.exists():
            raise CommandError(f"нет файла правил: {RULES_PATH}")
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        rules = data.get("rules") or []
        for rule in rules:
            rule["_re"] = re.compile(rule["match"])
        if only:
            rules = [rule for rule in rules if rule["id"] == only]
            if not rules:
                raise CommandError(f"правило не найдено: {only}")
        return rules

    @staticmethod
    def _first_match(rules: list[dict], name: str) -> tuple[dict, str] | None:
        for rule in rules:
            if rule["_re"].match(name):
                return rule, rule["_re"].sub(rule["replace"], name)
        return None

    @staticmethod
    def _apply(product: Product, restored: str, rule: dict) -> int:
        command = provenance.SourcedValueCommand(
            product_id=product.pk,
            target_kind="name",
            attribute_slug="",
            value={"type": "text", "value": restored},
            source="rules",
            confidence=float(rule.get("confidence", 0.75)),
            observed_value_hash=provenance.value_hash(product.name or ""),
            observed_source=(product.content_field_sources or {}).get("name", ""),
        )
        with transaction.atomic():
            result = provenance.apply_sourced_value(command)
        return 1 if result.status == "applied" else 0
