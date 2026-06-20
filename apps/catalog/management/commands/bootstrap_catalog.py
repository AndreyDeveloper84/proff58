"""Полный бутстрап каталога: дерево → tool_type → товары → обогащение → характеристики.

Вызывает идемпотентные команды по порядку. Повторный запуск не плодит дубли.
Характеристики (Фаза B, #96) идут ПОСЛЕ enrich_tool_type: enrich_attributes берёт
tool_type товара из его PAV (value_option.slug). Числа итогов — в админке (ImportRun)
и в выводе команд.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

STEPS = [
    "build_categories",
    "load_tool_types",
    "import_products",
    "enrich_tool_type",
    "load_attributes",
    "enrich_attributes",
]


class Command(BaseCommand):
    help = "Запустить весь бутстрап каталога (build_categories → … → enrich_attributes)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с входными файлами data/")

    def handle(self, *args, **options):
        path = options["path"]
        for step in STEPS:
            self.stdout.write(self.style.MIGRATE_HEADING(f"==> {step}"))
            kwargs = {"path": path} if path else {}
            call_command(step, **kwargs)
        self.stdout.write(self.style.SUCCESS("Бутстрап каталога завершён."))
