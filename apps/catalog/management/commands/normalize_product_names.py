"""Раскрытие сокращений в витринных названиях товаров.

Названия пришли из 1С телеграфной записью — «Перф. Bosch GBH 2-23REA», «Круг
алмаз. отрез. 115х1,0». Команда раскрывает сокращения в ``Product.name``
(страница товара, заголовок вкладки, поиск) и кладёт исходную короткую запись в
``Product.card_name`` — её показывает плитка каталога, где длинному названию
места нет.

Правила и их ограничения — в ``apps.catalog.name_normalization``.

Порядок выката (строго):

    normalize_product_names --dry-run --in-stock --report /tmp/wave1.csv  # волна 1: глазами
    normalize_product_names --in-stock                                    # волна 1: записать
    normalize_product_names --dry-run                                     # волна 2: объём
    normalize_product_names                                               # волна 2: записать

Идемпотентна: повторный прогон ничего не меняет. Импорт из 1С витринное имя не
перезаписывает (кладёт исходник в ``original_name``), так что обмен результат не
затрёт — см. apps/sync_1c/product_writer.py.
"""

from __future__ import annotations

import csv

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
            "--in-stock",
            action="store_true",
            help="Только позиции на остатках — первая волна выката (см. DRF-1602).",
        )
        parser.add_argument(
            "--report",
            metavar="ПУТЬ",
            help="Выгрузить «было → стало» в CSV для проверки глазами до записи.",
        )
        parser.add_argument(
            "--from-original",
            action="store_true",
            help=(
                "Считать витринное имя заново от строки 1С (original_name), а не от "
                "текущего name. Так откатывают неудачное правило: ручные правки при "
                "этом теряются, поэтому по умолчанию выключено."
            ),
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
        in_stock = options["in_stock"]
        from_original = options["from_original"]
        report_path = options["report"]

        changed: list[Product] = []
        shown = 0
        stats = {"total": 0, "name_changed": 0, "card_changed": 0, "expanded": 0}

        queryset = Product.objects.only(
            "id", "name", "original_name", "card_name", "article"
        ).order_by("id")
        if in_stock:
            queryset = queryset.filter(available_quantity__gt=0)

        report = None
        writer = None
        if report_path:
            report = open(report_path, "w", encoding="utf-8", newline="")
            writer = csv.writer(report)
            writer.writerow(["id", "было", "стало", "плитка", "раскрыто сокращение"])

        for product in queryset.iterator(chunk_size=BATCH):
            stats["total"] += 1
            source_name = product.original_name if from_original else product.name
            full = normalize_name(source_name or product.name, article=product.article)
            # Короткую форму считаем от строки 1С, а не от витринного имени:
            # иначе повторный прогон возьмёт уже развёрнутое `name` и плитка
            # потеряет телеграфную запись, ради которой card_name и заведён.
            source = product.original_name or product.name
            short = card_name(source, article=product.article)
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

            if writer is not None and (expanded or not only_changed):
                writer.writerow([product.id, product.name, full, short, "да" if expanded else ""])

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

        if report is not None:
            report.close()

        self.stdout.write("")
        if in_stock:
            self.stdout.write(self.style.WARNING("Срез: только позиции на остатках.\n"))
        if from_original:
            self.stdout.write(
                self.style.WARNING("Имя пересчитано от original_name: ручные правки затёрты.\n")
            )
        self.stdout.write(f"Всего товаров:        {stats['total']}")
        self.stdout.write(f"Изменится name:       {stats['name_changed']}")
        self.stdout.write(f"Изменится card_name:  {stats['card_changed']}")
        self.stdout.write(f"Раскрыто сокращений:  {stats['expanded']}")
        if report_path:
            self.stdout.write(f"Отчёт:                {report_path}")
        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run: в базу ничего не записано."))
        else:
            self.stdout.write(self.style.SUCCESS("\nГотово."))

    @staticmethod
    def _flush(batch: list[Product]) -> None:
        with transaction.atomic():
            Product.objects.bulk_update(batch, ["name", "card_name"])
