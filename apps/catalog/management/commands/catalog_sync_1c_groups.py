"""Синхронизировать реестр групп 1С (OneCGroup) — два источника.

Источник истины:
  * структура/код/иерархия — ``data/group_mapping.json`` (external_id + group_1c + site_path);
  * живость/счётчики товаров — ``Product.source_group`` (последняя выгрузка 1С).

Статусы:
  * ``active``     — группа из маппинга, по которой есть товары;
  * ``stale``      — группа из маппинга, но товаров по ней больше нет;
  * ``discovered`` — встретилась в ``source_group``, но в маппинге её нет (надо сопоставить).

    ./manage.py catalog_sync_1c_groups            # dry-run (что изменится)
    ./manage.py catalog_sync_1c_groups --commit    # применить

Идемпотентно (upsert по имени группы). Дерево сайта НЕ трогает.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.catalog.ingest import load_group_mapping
from apps.catalog.models import OneCGroup, OneCGroupStatus, Product


class Command(BaseCommand):
    help = "Синхронизировать реестр групп 1С (OneCGroup) из group_mapping.json + source_group."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")
        parser.add_argument(
            "--reset-mapping",
            dest="reset_mapping",
            action="store_true",
            help="Обнулить mapped_category у всех групп (чистое состояние «только из 1С»).",
        )

    def handle(self, *args, **options):
        try:
            mapping = load_group_mapping()
        except (FileNotFoundError, ValueError) as exc:
            self.stderr.write(self.style.ERROR(f"Не прочитать group_mapping.json: {exc}"))
            return

        # Живые счётчики по source_group.
        counts: Counter[str] = Counter()
        for row in (
            Product.objects.exclude(source_group="").values("source_group").annotate(n=Count("id"))
        ):
            counts[row["source_group"]] = row["n"]

        plan = []  # (name, code, site_path, count, status)
        seen: set[str] = set()
        for row in mapping:
            name = (row.get("group_1c") or "").strip()
            if not name:
                continue
            seen.add(name)
            code = str(row.get("external_id") or "")
            site_path = list(row.get("site_path") or [])
            cnt = counts.get(name, 0)
            status = OneCGroupStatus.ACTIVE if cnt > 0 else OneCGroupStatus.STALE
            plan.append((name, code, site_path, cnt, status))

        # Discovered: source_group вне маппинга.
        for name, cnt in counts.items():
            if name in seen:
                continue
            plan.append((name, "", [], cnt, OneCGroupStatus.DISCOVERED))

        self._report(plan)
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit.")
            )
            return

        reset = options["reset_mapping"]
        with transaction.atomic():
            for name, code, site_path, cnt, status in plan:
                # mapped_category НЕ авто-проставляем: на создании — пусто (сопоставление
                # делает куратор), на апдейте — НЕ трогаем его выбор. --reset-mapping явно
                # обнуляет (чистое состояние «только что из 1С, ничего не делали»).
                defaults = {
                    "code": code,
                    "site_path": site_path,
                    "product_count": cnt,
                    "status": status,
                }
                if reset:
                    defaults["mapped_category"] = None
                OneCGroup.objects.update_or_create(name=name, defaults=defaults)
        note = " (mapped_category обнулён)" if reset else ""
        self.stdout.write(
            self.style.SUCCESS(f"\nCOMMIT: синхронизировано групп {len(plan)}{note}.")
        )

    # ------------------------------------------------------------------ #
    def _report(self, plan):
        w = self.stdout.write
        by_status = Counter(p[4] for p in plan)
        prod_total = sum(p[3] for p in plan)
        w(self.style.MIGRATE_HEADING("\n=== Синхронизация групп 1С (dry-run) ==="))
        w(f"Всего групп: {len(plan)} | товаров покрыто (по source_group): {prod_total}")
        w(
            f"  active={by_status.get(OneCGroupStatus.ACTIVE, 0)} "
            f"stale={by_status.get(OneCGroupStatus.STALE, 0)} "
            f"discovered={by_status.get(OneCGroupStatus.DISCOVERED, 0)}"
        )
        disc = [p for p in plan if p[4] == OneCGroupStatus.DISCOVERED and p[3] > 0]
        if disc:
            w(self.style.WARNING("\nDiscovered (нет в маппинге) — топ по товарам:"))
            for name, _c, _sp, cnt, _st in sorted(disc, key=lambda x: -x[3])[:20]:
                w(f"  {cnt:6d}  {name[:60]}")
