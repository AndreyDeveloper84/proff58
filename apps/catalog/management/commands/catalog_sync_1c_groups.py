"""Синхронизировать реестр групп 1С (OneCGroup) с иерархией.

Источники:
  * ИЕРАРХИЯ/код/имя — ``data/catalog_fixed.json`` (дерево узлов 1С: группы
    ``ProductGroup=="1"`` с детьми → даёт родителя для каждой группы);
  * путь на сайте — ``data/group_mapping.json`` (``site_path``, справочно);
  * живость/счётчики — ``Product.source_group`` (последняя выгрузка 1С).

Статусы:
  * ``active``     — есть товары (по ``source_group``);
  * ``stale``      — группа есть в дереве 1С, но прямых товаров нет (часто это
    структурный родитель — товары лежат в дочерних);
  * ``discovered`` — встретилась в ``source_group``, но в дереве 1С её нет.

    ./manage.py catalog_sync_1c_groups                      # dry-run
    ./manage.py catalog_sync_1c_groups --commit             # применить
    ./manage.py catalog_sync_1c_groups --commit --reset-mapping  # + обнулить сопоставление

Идемпотентно (upsert по имени; родитель проставляется вторым проходом).
``mapped_category`` синк НЕ трогает (на создании пусто, на апдейте сохраняется выбор
куратора), кроме ``--reset-mapping``. Дерево сайта НЕ трогает.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.catalog.ingest import GROUP_NODE, load_group_mapping, load_json
from apps.catalog.models import OneCGroup, OneCGroupStatus, Product


def _walk_groups(nodes, parent_name=None):
    """Обойти дерево 1С, отдавая (name, code, parent_name) для узлов-групп."""
    for n in nodes:
        if str(n.get("ProductGroup", "")) != GROUP_NODE:
            continue
        name = (n.get("name") or "").strip()
        if not name:
            continue
        code = str(n.get("external_id") or "")
        yield (name, code, parent_name)
        yield from _walk_groups(n.get("children") or [], name)


class Command(BaseCommand):
    help = "Синхронизировать реестр групп 1С (OneCGroup) с иерархией из catalog_fixed.json."

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
            tree = load_json("catalog_fixed.json")
        except (FileNotFoundError, ValueError) as exc:
            self.stderr.write(self.style.ERROR(f"Не прочитать catalog_fixed.json: {exc}"))
            return
        site_path_by_name = {}
        try:
            for row in load_group_mapping():
                nm = (row.get("group_1c") or "").strip()
                if nm:
                    site_path_by_name[nm] = list(row.get("site_path") or [])
        except (FileNotFoundError, ValueError):
            pass  # site_path — справочный, не критичный

        # Живые счётчики по source_group.
        counts: Counter[str] = Counter()
        for row in (
            Product.objects.exclude(source_group="").values("source_group").annotate(n=Count("id"))
        ):
            counts[row["source_group"]] = row["n"]

        # Группы из дерева 1С (уникализируем по имени, родитель — первый встреченный).
        groups: dict[str, tuple[str, str | None]] = {}  # name -> (code, parent_name)
        for name, code, parent_name in _walk_groups(tree if isinstance(tree, list) else [tree]):
            groups.setdefault(name, (code, parent_name))

        # Discovered: source_group вне дерева.
        discovered = [n for n in counts if n not in groups]

        self._report(groups, discovered, counts)
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit.")
            )
            return

        reset = options["reset_mapping"]
        with transaction.atomic():
            # Пас 1: upsert всех групп (без родителя), счётчики/статус.
            for name, (code, _parent) in groups.items():
                cnt = counts.get(name, 0)
                status = OneCGroupStatus.ACTIVE if cnt > 0 else OneCGroupStatus.STALE
                self._upsert(name, code, site_path_by_name.get(name, []), cnt, status, reset)
            for name in discovered:
                self._upsert(name, "", [], counts[name], OneCGroupStatus.DISCOVERED, reset)

            # Пас 2: проставить родителя по имени.
            by_name = {g.name: g for g in OneCGroup.objects.all()}
            for name, (_code, parent_name) in groups.items():
                node = by_name.get(name)
                parent = by_name.get(parent_name) if parent_name else None
                if node and node.parent_id != (parent.id if parent else None):
                    node.parent = parent
                    node.save(update_fields=["parent"])

        note = " (mapped_category обнулён)" if reset else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: групп {len(groups)} (+ discovered {len(discovered)}){note}."
            )
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _upsert(name, code, site_path, cnt, status, reset):
        defaults = {"code": code, "site_path": site_path, "product_count": cnt, "status": status}
        if reset:
            defaults["mapped_category"] = None
        OneCGroup.objects.update_or_create(name=name, defaults=defaults)

    def _report(self, groups, discovered, counts):
        w = self.stdout.write
        active = sum(1 for n in groups if counts.get(n, 0) > 0)
        stale = len(groups) - active
        prod_total = sum(counts.values())
        roots = [n for n, (_c, p) in groups.items() if not p]
        w(self.style.MIGRATE_HEADING("\n=== Синхронизация групп 1С (dry-run) ==="))
        w(f"Групп в дереве 1С: {len(groups)} (корней {len(roots)}) | товаров: {prod_total}")
        w(f"  active={active} stale={stale} discovered={len(discovered)}")
        if discovered:
            w(self.style.WARNING("\nDiscovered (нет в дереве 1С) — топ по товарам:"))
            for n in sorted(discovered, key=lambda x: -counts[x])[:15]:
                w(f"  {counts[n]:6d}  {n[:60]}")
