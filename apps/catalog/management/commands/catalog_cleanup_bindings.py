"""Уборка привязок характеристик: снять мёртвые, пристроить бесхозные (DRF-1428, A1/A3).

Две правки, обе про привязки и ни одна — про наполнение:

* **Мёртвые привязки.** ``CategoryAttribute`` на категории, до которой покупатель не
  доходит (она или её предок сняты с витрины), не обслуживает никого. Такие строки
  снимаем — но только убедившись, что этот же атрибут привязан где-то в живом дереве.
  Иначе снятие не уберёт мусор, а потеряет единственную привязку фасета.
* **Бесхозные атрибуты.** ``Attribute`` без единой привязки в фильтр не попадёт
  никогда. Такие атрибуты привязываем к категории, в которой лежат их значения, с
  ``is_filter=False``: характеристика остаётся на карточке товара, сайдбар не
  засоряется. Удалять не станем — вместе с атрибутом ушли бы и значения, добытые
  парсером; вычистить дубли словаря должен трек наполнения, а не эта команда.

    ./manage.py catalog_cleanup_bindings                  # dry-run, ничего не пишет
    ./manage.py catalog_cleanup_bindings --commit         # применить + снимок отката
    ./manage.py catalog_cleanup_bindings --rollback FILE  # вернуть как было

Идемпотентна: повторный прогон после ``--commit`` показывает пустой план.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facet_audit import visible_categories
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Attribute, CategoryAttribute, ProductAttributeValue

#: Сколько значений атрибута считаем «следом эксперимента», а не полноценной осью.
#: Больше — повод разобраться руками, а не пристраивать автоматически.
MAX_ORPHAN_VALUES = 50


class Command(BaseCommand):
    help = "Снять привязки характеристик с невидимых категорий, пристроить бесхозные атрибуты."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit", action="store_true", help="Применить (по умолчанию dry-run)."
        )
        parser.add_argument("--rollback", metavar="FILE", help="Вернуть изменения по снимку.")
        parser.add_argument(
            "--skip-dead", action="store_true", help="Не трогать привязки невидимых категорий."
        )
        parser.add_argument(
            "--skip-orphans", action="store_true", help="Не пристраивать бесхозные атрибуты."
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])

        visible = visible_categories()
        dead = [] if options["skip_dead"] else self._plan_dead(visible)
        orphans = [] if options["skip_orphans"] else self._plan_orphans()

        self._report(dead, orphans)
        if not (dead or orphans):
            self.stdout.write(self.style.SUCCESS("\nЧисто: убирать нечего."))
            return
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit.")
            )
            return
        self._commit(dead, orphans)

    # ------------------------------------------------------------------ #
    def _plan_dead(self, visible) -> list[CategoryAttribute]:
        """Привязки на невидимых категориях, чей атрибут жив в видимом дереве."""
        vis_ids = {c.id for c in visible}
        bindings = list(CategoryAttribute.objects.select_related("category", "attribute"))
        live_attr_ids = {ca.attribute_id for ca in bindings if ca.category_id in vis_ids}
        plan, kept = [], []
        for ca in bindings:
            if ca.category_id in vis_ids:
                continue
            (plan if ca.attribute_id in live_attr_ids else kept).append(ca)
        for ca in kept:
            self.stdout.write(
                self.style.WARNING(
                    f"ОСТАВЛЕНО: `{ca.attribute.slug}` живёт только на невидимой "
                    f"«{ca.category.name}» — снятие потеряло бы фасет. "
                    "Сначала привяжите атрибут к живой категории."
                )
            )
        return sorted(plan, key=lambda ca: (ca.category.path, ca.attribute.slug))

    def _plan_orphans(self) -> list[tuple[Attribute, int, int]]:
        """(атрибут, id категории значений, число значений) для атрибутов без привязок."""
        plan = []
        for attr in Attribute.objects.filter(category_attributes__isnull=True):
            rows = ProductAttributeValue.objects.filter(attribute=attr).values_list(
                "product__category_id", flat=True
            )
            cats = {c for c in rows if c is not None}
            n = len(rows)
            if not cats:
                self.stdout.write(
                    self.style.WARNING(
                        f"ПРОПУЩЕН: `{attr.slug}` — ни одного значения, привязать не к чему."
                    )
                )
                continue
            if len(cats) > 1 or n > MAX_ORPHAN_VALUES:
                self.stdout.write(
                    self.style.WARNING(
                        f"ПРОПУЩЕН: `{attr.slug}` — {n} значений в {len(cats)} категориях, "
                        "нужен ручной разбор (куратор словаря)."
                    )
                )
                continue
            plan.append((attr, cats.pop(), n))
        return plan

    # ------------------------------------------------------------------ #
    def _report(self, dead, orphans):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING("\n=== Уборка привязок характеристик ==="))
        w(f"\nК снятию (привязки невидимых категорий): {len(dead)}")
        for ca in dead:
            w(f"  {ca.category.slug:34s} depth={ca.category.depth}  {ca.attribute.slug}")
        w(f"\nК привязке (бесхозные атрибуты): {len(orphans)}")
        for attr, cat_id, n in orphans:
            w(f"  {attr.slug:22s} → категория id={cat_id}  значений={n}  is_filter=False")

    def _commit(self, dead, orphans):
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        path = backup_dir / f"cleanup-bindings-{timezone.now():%Y%m%d-%H%M%S}.json"

        removed = [
            {
                "category_id": ca.category_id,
                "attribute_id": ca.attribute_id,
                "is_required": ca.is_required,
                "is_filter": ca.is_filter,
                "group": ca.group,
                "is_seo_facet": ca.is_seo_facet,
                "sort_order": ca.sort_order,
            }
            for ca in dead
        ]
        with transaction.atomic():
            if dead:
                CategoryAttribute.objects.filter(id__in=[ca.id for ca in dead]).delete()
            created = [
                CategoryAttribute.objects.create(
                    category_id=cat_id, attribute=attr, is_filter=False
                ).pk
                for attr, cat_id, _n in orphans
            ]
            # Снимок пишем в той же транзакции: файл без записи в БД (или наоборот)
            # сделал бы откат враньём.
            path.write_text(
                json.dumps({"removed": removed, "created": created}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: снято {len(removed)}, создано {len(created)}. Снимок отката: {path}"
            )
        )

    # ------------------------------------------------------------------ #
    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Снимок не найден: {file_path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CommandError(f"Битый JSON: {exc}") from exc
        with transaction.atomic():
            CategoryAttribute.objects.filter(id__in=data.get("created", [])).delete()
            for row in data.get("removed", []):
                CategoryAttribute.objects.update_or_create(
                    category_id=row["category_id"],
                    attribute_id=row["attribute_id"],
                    defaults={
                        k: v for k, v in row.items() if k not in ("category_id", "attribute_id")
                    },
                )
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK: возвращено {len(data.get('removed', []))}, "
                f"удалено {len(data.get('created', []))}."
            )
        )
