"""Раскрытие сокращений в витринных названиях товаров.

Названия пришли из 1С телеграфной записью — «Перф. Bosch GBH 2-23REA», «Круг
алмаз. отрез. 115х1,0». Команда раскрывает сокращения в ``Product.name``
(страница товара, заголовок вкладки, поиск) и кладёт исходную короткую запись в
``Product.card_name`` — её показывает плитка каталога, где длинному названию
места нет.

Правила и их ограничения — в ``apps.catalog.name_normalization``.

Порядок выката (строго):

    normalize_product_names --dry-run --limit 50   # посмотреть, что получится
    normalize_product_names --dry-run              # сколько всего затронет
    normalize_product_names                        # записать

Идемпотентна: повторный прогон ничего не меняет. Импорт из 1С витринное имя не
перезаписывает (кладёт исходник в ``original_name``), так что обмен результат не
затрёт — см. apps/sync_1c/product_writer.py.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product
from apps.catalog.name_normalization import card_name, normalize_name

# Размер пачки для bulk_update: 47 тысяч товаров одним запросом класть незачем.
BATCH = 500


class Command(BaseCommand):
    help = "Раскрыть сокращения в названиях товаров (name), короткую форму — в card_name."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только отчёт: показать примеры и счётчики, ничего не записывать.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Показать не больше N примеров изменений (0 — только счётчики).",
        )
        parser.add_argument(
            "--only-changed",
            action="store_true",
            help="В примеры включать лишь те, где раскрылось сокращение (без косметики).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        only_changed = options["only_changed"]

        changed: list[Product] = []
        shown = 0
        stats = {"total": 0, "name_changed": 0, "card_changed": 0, "expanded": 0}

        queryset = Product.objects.only("id", "name", "card_name").order_by("id")
        for product in queryset.iterator(chunk_size=BATCH):
            stats["total"] += 1
            full = normalize_name(product.name)
            short = card_name(product.name)
            # Раскрытие сокращения, а не просто прибранные пробелы: только такие
            # правки стоит смотреть глазами.
            expanded = full != short
            if expanded:
                stats["expanded"] += 1

            if full == product.name and short == product.card_name:
                continue
            if full != product.name:
                stats["name_changed"] += 1
            if short != product.card_name:
                stats["card_changed"] += 1

            if shown < limit and (expanded or not only_changed):
                shown += 1
                self.stdout.write(f"  было:  {product.name}")
                self.stdout.write(self.style.SUCCESS(f"  стало: {full}"))
                if short != full:
                    self.stdout.write(f"  плитка: {short}")
                self.stdout.write("")

            product.name = full
            product.card_name = short
            changed.append(product)

            if not dry_run and len(changed) >= BATCH:
                self._flush(changed)
                changed = []

        if not dry_run and changed:
            self._flush(changed)

        self.stdout.write("")
        self.stdout.write(f"Всего товаров:        {stats['total']}")
        self.stdout.write(f"Изменится name:       {stats['name_changed']}")
        self.stdout.write(f"Изменится card_name:  {stats['card_changed']}")
        self.stdout.write(f"Раскрыто сокращений:  {stats['expanded']}")
        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run: в базу ничего не записано."))
        else:
            self.stdout.write(self.style.SUCCESS("\nГотово."))

    @staticmethod
    def _flush(batch: list[Product]) -> None:
        with transaction.atomic():
            Product.objects.bulk_update(batch, ["name", "card_name"])
