"""Загрузка связей товар↔товар из JSON («покупают вместе», аналоги).

Вход — результат разбора подгруппы (см. ``export_link_candidates``):

    {
      "kind": "analog",              // analog | cross_sell
      "origin": "ai",                // ai | manual (по умолчанию ai)
      "links": [
        {"source": 123, "targets": [456, 789]},
        ...
      ]
    }

Команда только ДОПИСЫВАЕТ связи: снимать отмеченное менеджером разбор не вправе.
Связи взаимные, поэтому пара A↔B ставится один раз, в каком бы порядке она ни
пришла. Повторный прогон того же файла ничего не меняет.

    python manage.py apply_product_links --file links.json --dry-run
    python manage.py apply_product_links --file links.json
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.links import add_links
from apps.catalog.models import CompatibilityKind, CompatibilityOrigin, Product

ALLOWED_KINDS = {CompatibilityKind.CROSS_SELL.value, CompatibilityKind.ANALOG.value}


class Command(BaseCommand):
    help = "Загрузить связи «покупают вместе» / «аналоги» из JSON"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="JSON с разбором")
        parser.add_argument(
            "--dry-run", action="store_true", help="Показать, что будет сделано, и выйти"
        )

    def handle(self, *args, **opts):
        with open(opts["file"], encoding="utf-8") as fh:
            data = json.load(fh)

        kind = data.get("kind")
        if kind not in ALLOWED_KINDS:
            raise CommandError(f"kind должен быть одним из {sorted(ALLOWED_KINDS)}, пришло: {kind}")
        origin = data.get("origin", CompatibilityOrigin.AI)
        if origin not in CompatibilityOrigin.values:
            raise CommandError(f"origin должен быть одним из {CompatibilityOrigin.values}")

        rows = data.get("links") or []
        wanted_ids = {int(r["source"]) for r in rows} | {
            int(t) for r in rows for t in r.get("targets", [])
        }
        known = set(Product.objects.filter(pk__in=wanted_ids).values_list("pk", flat=True))
        missing = wanted_ids - known
        if missing:
            self.stdout.write(
                self.style.WARNING(f"Нет таких товаров ({len(missing)}): {sorted(missing)[:20]}")
            )

        planned = 0
        created = 0
        for row in rows:
            source_id = int(row["source"])
            if source_id not in known:
                continue
            targets = [int(t) for t in row.get("targets", []) if int(t) in known]
            if not targets:
                continue
            planned += len(targets)
            if opts["dry_run"]:
                continue
            product = Product.objects.get(pk=source_id)
            created += add_links(product, kind, targets, origin=origin)

        if opts["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Сухой прогон: {len(rows)} товаров, {planned} пар вида «{kind}». "
                    "Ничего не записано."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: обработано {len(rows)} товаров, новых связей «{kind}» — {created} "
                f"(из {planned} пар; остальные уже были)."
            )
        )
