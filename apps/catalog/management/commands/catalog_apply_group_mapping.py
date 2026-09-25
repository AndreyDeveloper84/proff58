"""Применить сопоставление «группа 1С → категория сайта» (расставить товары).

Переносит товары групп (по ``Product.source_group``) в их ``mapped_category``,
помечая ``category_is_manual=True`` (сопоставление куратора авторитетно).

    ./manage.py catalog_apply_group_mapping --all                 # dry-run по всем
    ./manage.py catalog_apply_group_mapping --all --commit         # применить все
    ./manage.py catalog_apply_group_mapping --group "Биты" --commit # одна группа

Учитываются только группы с заданной ``mapped_category``. Сбрасывает кэш.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import OneCGroup, Product
from apps.catalog.onec_groups import apply_group_mapping


class Command(BaseCommand):
    help = "Применить сопоставление групп 1С → категории (расставить товары по source_group)."

    def add_arguments(self, parser):
        parser.add_argument("--group", help="Имя одной группы 1С.")
        parser.add_argument("--all", action="store_true", help="Все группы с mapped_category.")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        if not options["group"] and not options["all"]:
            raise CommandError("Укажите --group <имя> или --all.")
        qs = OneCGroup.objects.exclude(mapped_category__isnull=True)
        if options["group"]:
            qs = qs.filter(name=options["group"])
        groups = list(qs)
        if not groups:
            self.stdout.write(self.style.WARNING("Нет групп с заданной категорией под условие."))
            return

        w = self.stdout.write
        w(self.style.MIGRATE_HEADING("\n=== Применение сопоставления групп → категории ==="))
        total = 0
        for g in groups:
            n = Product.objects.filter(source_group=g.name, category_is_manual=False).count()
            total += n
            w(f"  {g.name[:40]:40s} → {g.mapped_category}  товаров: {n}")
        w(self.style.SUCCESS(f"\nГрупп: {len(groups)}; перенесём товаров: ~{total}"))

        if not options["commit"]:
            w(self.style.WARNING("\nDRY-RUN: ничего не перенесено. Применить — --commit."))
            return

        moved = sum(apply_group_mapping(g) for g in groups)
        w(self.style.SUCCESS(f"\nCOMMIT: перенесено товаров {moved} (category_is_manual=True)."))
