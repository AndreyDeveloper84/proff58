"""Распределение grab-bag legacy-раздела по v2-разделам (dry-run + откат). Стаб/TDD."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductAttributeValue, ProductStatus
from apps.catalog.queries import _subtree_ids
from apps.core.events import EventSource, product_updated

TOOL_TYPE_SLUG = "tool_type"
DISTRIBUTIONS = {
    "hoztovary": {
        "source": {"slug": "hoztovary-sad-ogorod", "name": "Хозтовары, сад, огород"},
        "targets": [
            {
                "slug": "sadovaya",
                "name": "Садовая техника и инвентарь",
                "tool_types": [
                    "hoz-lopaty",
                    "hoz-metly",
                    "hoz-vily",
                    "hoz-grabli",
                    "hoz-opryskivateli",
                    "hoz-shlangi",
                    "hoz-setki",
                    "hoz-kolesa",
                ],
            },
            {
                "slug": "krepezh",
                "name": "Крепёж и метизы",
                "tool_types": [
                    "hoz-zamki",
                    "hoz-furnitura",
                    "hoz-trosy",
                    "hoz-provoloka",
                    "hoz-homuty",
                ],
            },
            {
                "slug": "ruchnoy",
                "name": "Ручной инструмент",
                "tool_types": ["hoz-lezviya", "hoz-nozhi", "hoz-steklorezy"],
            },
            {
                "slug": "stroitelnyy",
                "name": "Строительный и отделочный инструмент",
                "tool_types": ["hoz-plenka"],
            },
            {
                "slug": "izmeritelnyy",
                "name": "Измерительный инструмент",
                "tool_types": ["hoz-lupy"],
            },
        ],
        "exclude_ids": [41648, 41650],  # FP hoz-plenka (оба pub=0): ламинирование А4, плёнка Huawei
    },
}


def _published(ids):
    return Product.objects.filter(
        id__in=ids, is_active=True, status=ProductStatus.PUBLISHED
    ).count()


class Command(BaseCommand):
    help = "Распределение legacy-раздела по v2-разделам: dry-run / --commit / --rollback."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=sorted(DISTRIBUTIONS))
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")
        parser.add_argument("--exclude-ids", default="")

    def handle(self, *args, **options):
        if options.get("rollback"):
            return self._rollback(options["rollback"])
        if not options.get("source"):
            raise CommandError("Укажите --source или --rollback FILE.")
        source = options["source"]
        cfg = DISTRIBUTIONS[source]
        src = self._resolve(cfg["source"])
        targets = [(t, self._resolve(t)) for t in cfg["targets"]]
        missing = [s["slug"] for s, c in [(cfg["source"], src), *targets] if c is None]
        if missing:
            raise CommandError("Не найдены категории (по slug/name): " + ", ".join(missing))
        exclude = set(cfg.get("exclude_ids", []))
        raw = (options.get("exclude_ids") or "").strip()
        if raw:
            exclude |= {int(x) for x in raw.split(",") if x.strip()}
        plan = self._plan(src, targets, exclude)
        self._report(source, src, targets, plan)
        if options.get("commit"):
            self._commit(source, src, targets, plan)
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: изменения НЕ применены. Для применения добавьте --commit."
                )
            )

    def _resolve(self, spec):
        return (
            Category.objects.filter(slug=spec["slug"]).first()
            or Category.objects.filter(name=spec["name"]).first()
        )

    def _plan(self, src, targets, exclude):
        source_prod = set(
            Product.objects.filter(category_id__in=_subtree_ids(src)).values_list("id", flat=True)
        )
        assign, conflicts, all_cluster = {}, 0, set()
        for idx, (spec, _cat) in enumerate(targets):
            tt_pids = set(
                ProductAttributeValue.objects.filter(
                    attribute__slug=TOOL_TYPE_SLUG,
                    value_option__slug__in=spec["tool_types"],
                ).values_list("product_id", flat=True)
            )
            in_source = tt_pids & source_prod
            all_cluster |= in_source
            for pid in in_source - exclude:
                if pid in assign:
                    conflicts += 1
                else:
                    assign[pid] = idx
        per_target = [[] for _ in targets]
        for pid, idx in assign.items():
            per_target[idx].append(pid)
        return {
            "per_target": per_target,
            "conflicts": conflicts,
            "excluded_present": len(all_cluster & exclude),
        }

    def _report(self, source, src, targets, plan):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"\n=== Распределение legacy «{source}» (dry-run отчёт) ==="))
        n_src = Product.objects.filter(category_id__in=_subtree_ids(src)).count()
        w(f"Источник: «{src.name}» id={src.pk} slug={src.slug} (товаров в поддереве: {n_src})")
        w(self.style.MIGRATE_HEADING("\n-- Перенос по кластерам (scoped по источнику) --"))
        total = total_pub = 0
        for (_spec, cat), ids in zip(targets, plan["per_target"], strict=True):
            pub = _published(ids)
            total += len(ids)
            total_pub += pub
            w(f"  → «{cat.name}» ({cat.slug}): move {len(ids)} | published {pub}")
        w(self.style.SUCCESS(f"ИТОГО move: {total} | published: {total_pub}"))
        w(f"Исключено FP (по id): {plan['excluded_present']}")
        w(f"Конфликтов (товар в 2+ кластерах, взят первый): {plan['conflicts']}")

    def _commit(self, source, src, targets, plan):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{source}-{ts}.json"
        backup = {"source": source, "source_id": src.pk, "products": []}
        moved = []
        with transaction.atomic():
            for (_spec, cat), ids in zip(targets, plan["per_target"], strict=True):
                if not ids:
                    continue
                for r in Product.objects.filter(id__in=ids).values(
                    "id", "category_id", "category_is_manual"
                ):
                    backup["products"].append(
                        dict(
                            id=r["id"],
                            category_id=r["category_id"],
                            category_is_manual=r["category_is_manual"],
                        )
                    )
                Product.objects.filter(id__in=ids).update(category=cat, category_is_manual=True)
                moved += ids
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))

            def _emit(ids=tuple(moved)):
                for pid in ids:
                    product_updated.send(
                        sender=Product,
                        product_id=pid,
                        source=EventSource.SYSTEM,
                        changed_fields=["category"],
                    )

            transaction.on_commit(_emit)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: перенесено {len(moved)} товаров. Снимок отката: {backup_path}"
            )
        )

    def _rollback(self, file_path):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Файл снимка не найден: {file_path}")
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise CommandError(f"Битый JSON снимка: {exc}") from exc
        with transaction.atomic():
            for r in data.get("products", []):
                Product.objects.filter(id=r["id"]).update(
                    category_id=r["category_id"], category_is_manual=r["category_is_manual"]
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK: восстановлено товаров {len(data.get('products', []))} из {path}."
            )
        )
