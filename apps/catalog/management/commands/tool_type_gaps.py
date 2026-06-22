"""Отчёт по неразмеченным tool_type — драйвер следующей итерации словаря.

Read-only: читает ``EnrichmentLog`` последнего (или указанного) прогона обогащения
и печатает Top-N названий, ушедших в модерацию, плюс частоты первых слов — по верхним
категориям. Подсказывает, какие ключевые слова/типы добавить в ``tool_type_rules.json``,
чтобы поднять покрытие в следующем цикле.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from apps.catalog.models import EnrichmentLog, EnrichmentResult, ImportRun


class Command(BaseCommand):
    help = "Top-N неразмеченных tool_type (модерация) по категориям — для доводки словаря."

    def add_arguments(self, parser):
        parser.add_argument("--top", type=int, default=40, help="Сколько позиций показать")
        parser.add_argument(
            "--run", type=int, default=None, help="ID ImportRun (по умолчанию последний enrich)"
        )

    def handle(self, *args, **options):
        top = options["top"]
        run_id = options["run"]
        if run_id is None:
            run = (
                ImportRun.objects.filter(source="enrich_tool_type").order_by("-started_at").first()
            )
            if run is None:
                self.stderr.write("Не найдено ни одного прогона enrich_tool_type.")
                return
            run_id = run.id

        logs = EnrichmentLog.objects.filter(
            run_id=run_id, result=EnrichmentResult.MODERATION
        ).values_list("category_path", "raw_name")

        by_top: dict[str, list[str]] = {}
        for path, name in logs:
            by_top.setdefault((path or "").split(" / ")[0], []).append(name)

        self.stdout.write(self.style.MIGRATE_HEADING(f"Top-Unknown по прогону #{run_id}"))
        for topcat, names in sorted(by_top.items(), key=lambda kv: -len(kv[1])):
            self.stdout.write(self.style.SUCCESS(f"\n=== {topcat} — в модерации {len(names)} ==="))

            first_words = Counter(self._first_word(n) for n in names)
            self.stdout.write("  Частые первые слова:")
            for w, n in first_words.most_common(min(top, 25)):
                self.stdout.write(f"    {n:5d}  {w}")

            self.stdout.write("  Частые названия (нормализованные):")
            norm_names = Counter(self._norm(n) for n in names)
            for nm, n in norm_names.most_common(min(top, 15)):
                self.stdout.write(f"    {n:5d}  {nm[:70]}")

    @staticmethod
    def _norm(text: str) -> str:
        return (text or "").lower().replace("ё", "е").strip().lstrip("я ").strip()

    @classmethod
    def _first_word(cls, text: str) -> str:
        words = cls._norm(text).split()
        return words[0] if words else "—"
