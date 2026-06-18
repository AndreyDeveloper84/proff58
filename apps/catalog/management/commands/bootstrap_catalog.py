"""Полный бутстрап каталога: дерево → словарь tool_type → товары → обогащение.

Вызывает четыре идемпотентные команды по порядку. Повторный запуск не плодит
дубли. Числа итогов — в админке (ImportRun) и в выводе команд.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

STEPS = ["build_categories", "load_tool_types", "import_products", "enrich_tool_type"]


class Command(BaseCommand):
    help = "Запустить весь бутстрап каталога (build_categories → … → enrich_tool_type)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с входными файлами data/")

    def handle(self, *args, **options):
        path = options["path"]
        for step in STEPS:
            self.stdout.write(self.style.MIGRATE_HEADING(f"==> {step}"))
            kwargs = {"path": path} if path else {}
            call_command(step, **kwargs)
        self.stdout.write(self.style.SUCCESS("Бутстрап каталога завершён."))
