"""BRAND-02: контролируемое заполнение ``Product.brand`` из названия.

Dry-run по умолчанию. Запись разрешена ровно одному статусу — ``CREATE``.

Почему ``changed`` не существует как исход: обмен с 1С пишет бренд только в
пустое поле (``sync_1c/product_writer.py``: ``if item.brand and not
product.brand``), то есть первый, кто записал, владеет полем. Команда обязана
вести себя так же и после первого apply: если у товара уже есть бренд, а
извлечение предлагает другой — это ``CONFLICT`` на разбор, а не тихий update.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.brand_identity import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_COMPAT,
    IDENTITY_HIGH,
    IDENTITY_NONE,
    decide_brand,
)
from apps.catalog.brand_vocabulary import load_brand_vocabulary
from apps.catalog.models import Product

# Исходы по товару. Сумма обязана покрывать весь scope без остатка.
CREATE = "CREATE"
KEEP = "KEEP"
CONFLICT = "CONFLICT"
STATUSES = (CREATE, KEEP, CONFLICT, IDENTITY_COMPAT, IDENTITY_AMBIGUOUS, IDENTITY_NONE)


class Command(BaseCommand):
    help = "Заполнить Product.brand по названию (BRAND-02). По умолчанию dry-run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Выполнить запись. Без флага — dry-run, ни одной записи в БД.",
        )
        parser.add_argument("--in-stock-only", action="store_true", default=False)
        parser.add_argument("--active-only", action="store_true", default=False)
        parser.add_argument("--vocabulary", default=None, help="Путь к brand_vocabulary.json")
        parser.add_argument("--json-report", default=None, help="Файл машиночитаемого отчёта")
        parser.add_argument(
            "--rollback-artifact",
            default=None,
            help="Файл артефакта отката: product_id + old_brand + new_brand по каждой записи.",
        )
        parser.add_argument("--limit", type=int, default=0, help="Ограничить выборку (отладка)")

    def handle(self, *args, **options):
        apply_mode = options["apply"]
        if apply_mode and not options["rollback_artifact"]:
            raise CommandError(
                "--apply требует --rollback-artifact: без прежнего значения поля откат "
                "неотличим от «бренда никогда не было»."
            )
        vocabulary = (
            load_brand_vocabulary(Path(options["vocabulary"])) if options["vocabulary"] else None
        )

        filters = {}
        if options["in_stock_only"]:
            filters["available_quantity__gt"] = 0
        if options["active_only"]:
            filters["is_active"] = True
        qs = Product.objects.filter(**filters).only("id", "name", "original_name", "brand")
        if options["limit"]:
            qs = qs[: options["limit"]]

        rows: list[dict] = []
        counts: Counter = Counter()
        by_brand: Counter = Counter()
        conflicts: list[dict] = []
        examples: dict[str, list[dict]] = defaultdict(list)

        for product in qs.iterator(chunk_size=2000):
            name = product.original_name or product.name or ""
            current = (product.brand or "").strip()
            decision = decide_brand(name, vocabulary)

            if current:
                if decision.is_high and decision.brand != current:
                    status = CONFLICT
                else:
                    status = KEEP
            elif decision.status == IDENTITY_HIGH:
                status = CREATE
            else:
                status = decision.status

            counts[status] += 1
            if status == CREATE:
                by_brand[decision.brand] += 1
            row = {
                "product_id": product.id,
                "status": status,
                "old_brand": current,
                "new_brand": decision.brand if status == CREATE else "",
                "proposed": decision.brand,
                "manufacturers": list(decision.manufacturers),
                "compatibility_refs": list(decision.compatibility_refs),
                "name": name,
            }
            rows.append(row)
            if status == CONFLICT:
                conflicts.append(row)
            if len(examples[status]) < 5:
                examples[status].append(
                    {
                        "product_id": product.id,
                        "name": name[:90],
                        "proposed": decision.brand,
                        "refs": list(decision.compatibility_refs),
                    }
                )

        total = sum(counts.values())
        creates = [r for r in rows if r["status"] == CREATE]

        # AUTO_IDENTITY_READY считается ПОСЛЕ гипотетической записи: это целевая
        # метрика трека, а не «сколько брендов записали».
        written_ids = {r["product_id"] for r in creates}

        if apply_mode:
            with transaction.atomic():
                for chunk_start in range(0, len(creates), 1000):
                    chunk = creates[chunk_start : chunk_start + 1000]
                    ids = [r["product_id"] for r in chunk]
                    live = {p.id: p for p in Product.objects.select_for_update().filter(id__in=ids)}
                    to_save = []
                    for r in chunk:
                        p = live.get(r["product_id"])
                        if p is None:
                            continue
                        # Повторная сверка внутри транзакции: план строился вне неё.
                        if (p.brand or "").strip():
                            r["status"] = CONFLICT
                            conflicts.append(r)
                            continue
                        p.brand = r["new_brand"]
                        to_save.append(p)
                    Product.objects.bulk_update(to_save, ["brand"])

        self.stdout.write(f"scope: {total} товаров, режим: {'APPLY' if apply_mode else 'dry-run'}")
        for st in STATUSES:
            self.stdout.write(f"  {st:18} {counts.get(st, 0)}")
        self.stdout.write(f"  {'СУММА':18} {sum(counts.get(s, 0) for s in STATUSES)}")
        if sum(counts.get(s, 0) for s in STATUSES) != total:
            raise CommandError("сумма статусов не покрывает scope — отчёт неполон")
        self.stdout.write("\nтоп брендов к записи:")
        for brand, n in by_brand.most_common(15):
            self.stdout.write(f"  {brand:16} {n}")

        report = {
            "mode": "apply" if apply_mode else "dry-run",
            "scope": {
                "total": total,
                "in_stock_only": options["in_stock_only"],
                "active_only": options["active_only"],
            },
            "counts": {s: counts.get(s, 0) for s in STATUSES},
            "by_brand": dict(by_brand),
            "conflicts": conflicts,
            "examples": {k: v for k, v in examples.items()},
            "written": len(written_ids) if apply_mode else 0,
        }
        if options["json_report"]:
            Path(options["json_report"]).write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            self.stdout.write(f"\nотчёт: {options['json_report']}")
        if options["rollback_artifact"]:
            artifact = {
                "command": "catalog_fill_brand",
                "mode": report["mode"],
                "items": [
                    {
                        "product_id": r["product_id"],
                        "old_brand": r["old_brand"],
                        "new_brand": r["new_brand"],
                    }
                    for r in creates
                ],
            }
            Path(options["rollback_artifact"]).write_text(
                json.dumps(artifact, ensure_ascii=False), encoding="utf-8"
            )
            self.stdout.write(f"артефакт отката: {options['rollback_artifact']}")
