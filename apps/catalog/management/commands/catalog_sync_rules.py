"""E2 — мост «словарь → CategoryMappingRule»: новые товары 1С авто-классифицируются.

Генерирует regex-правила (`MappingRuleType.REGEX` + `exclude_pattern`) из
``data/product_type_rules.json``, нацеленные на уже построенные v2-узлы раздела
(см. `catalog_build_section`). После этого импорт 1С (`categorize()`) кладёт новые
товары раздела в те же узлы, что и массовый классификатор.

    ./manage.py catalog_sync_rules --section osnastka            # dry-run
    ./manage.py catalog_sync_rules --section osnastka --commit

Идемпотентно: на каждом прогоне авто-правила раздела (note `[auto:<slug>]`)
пересоздаются; ручные правила не трогаются. Приоритет авто-правил — 1000+
(ручные правила с меньшим приоритетом срабатывают раньше).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category, CategoryMappingRule, MappingRuleType
from apps.catalog.semantic import SECTION_RULES, load_rules

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
_AUTO_PRIORITY_BASE = 1000


class Command(BaseCommand):
    help = "Сгенерировать CategoryMappingRule (regex) из словаря на v2-узлы раздела."

    def add_arguments(self, parser):
        parser.add_argument("--section", default="osnastka", choices=sorted(SECTION_RULES))
        parser.add_argument("--rules", default=None, help="Переопределить файл словаря.")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--min-confidence", choices=["high", "medium"], default="medium")

    def handle(self, *args, **options):
        rules_path = options["rules"] or SECTION_RULES[options["section"]]
        try:
            doc, compiled = load_rules(rules_path)
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(f"Не прочитать правила: {exc}") from exc

        slug = doc.get("section_slug", options["section"])
        root = (
            Category.objects.filter(slug=slug).first()
            or Category.objects.filter(name=doc.get("section", "")).first()
        )
        if root is None:
            raise CommandError(
                f"Корень раздела (slug={slug}) не найден — сначала постройте раздел "
                "командой catalog_build_section."
            )

        min_rank = _CONF_RANK[options["min_confidence"]]
        # Готовим план правил: (priority, pattern, exclude, target_node, note).
        plan = []
        missing_nodes: set[str] = set()
        for idx, r in enumerate(doc.get("rules", [])):
            if _CONF_RANK.get(r.get("confidence", "medium"), 1) < min_rank:
                continue
            target = self._find_node(root, r["subcat"], r.get("subtype"))
            if target is None:
                missing_nodes.add(f"{r['subcat']}/{r.get('subtype') or '—'}")
                continue
            exclude = "|".join(r.get("exclude", []))
            label = f"[auto:{slug}] {r['subcat']}/{r.get('subtype') or '—'}"
            for kw in r.get("keywords", []):
                plan.append((_AUTO_PRIORITY_BASE + idx, kw, exclude, target, label))

        existing = CategoryMappingRule.objects.filter(note__startswith=f"[auto:{slug}]").count()
        self._report(slug, root, plan, existing, missing_nodes, options["min_confidence"])

        if options["commit"]:
            self._commit(slug, plan)
        else:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: правила не изменены. Применить — --commit.")
            )

    # ------------------------------------------------------------------ #
    def _find_node(self, root: Category, subcat: str, subtype: str | None):
        sc = root.get_children().filter(name=subcat).first()
        if sc is None:
            return None
        if subtype:
            return sc.get_children().filter(name=subtype).first() or sc
        return sc

    def _report(self, slug, root, plan, existing, missing_nodes, minconf):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"\n=== Синхронизация правил «{root.name}» (dry-run) ==="))
        w(f"Корень: id={root.pk} slug={slug}")
        w(f"Будет авто-правил (regex, confidence ≥ {minconf}): {len(plan)}")
        w(f"Существующих авто-правил [auto:{slug}] (будут пересозданы): {existing}")
        if missing_nodes:
            w(
                self.style.ERROR(
                    "  ВНИМАНИЕ: нет узлов под правила (пропущены): "
                    + ", ".join(sorted(missing_nodes))
                )
            )

    def _commit(self, slug, plan):
        with transaction.atomic():
            CategoryMappingRule.objects.filter(note__startswith=f"[auto:{slug}]").delete()
            CategoryMappingRule.objects.bulk_create(
                [
                    CategoryMappingRule(
                        rule_type=MappingRuleType.REGEX,
                        pattern=pattern,
                        exclude_pattern=exclude,
                        target_category=target,
                        priority=priority,
                        is_active=True,
                        note=note,
                    )
                    for priority, pattern, exclude, target, note in plan
                ]
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: создано авто-правил {len(plan)} (тип regex). Новые товары 1С "
                "раздела теперь авто-классифицируются в v2-узлы."
            )
        )
