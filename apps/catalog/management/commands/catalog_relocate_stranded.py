"""Перенос застрявших товаров в наличии из мёртвых legacy-корней в живое дерево (DRF-1438).

    ./manage.py catalog_relocate_stranded                       # dry-run: план и обоснование
    ./manage.py catalog_relocate_stranded --markdown отчёт.md   # план файлом на сверку глазами
    ./manage.py catalog_relocate_stranded --commit              # применить + снимок отката
    ./manage.py catalog_relocate_stranded --rollback FILE       # вернуть как было

Получателя команда выводит из дерева (см. ``apps/catalog/relocate.py``), а не берёт из
зашитой карты. Товары, для которых лист не выводится однозначно, в план не попадают —
они уходят в отчёт на решение человека.

Порядок по регламенту: dry-run → сверка глазами → ``pg_dump`` → ``--commit`` →
повторный dry-run (обязан дать пустой план).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Product
from apps.catalog.relocate import MIN_HOME_SHARE, MIN_LEAF_PRODUCTS, MIN_SHARE, build_plan
from apps.core.events import EventSource, product_updated


class Command(BaseCommand):
    help = "Перенести товары в наличии из категорий вне витрины в живые листья дерева."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")
        parser.add_argument("--markdown", metavar="FILE", help="Куда сложить план отчётом.")
        parser.add_argument("--csv", metavar="FILE", help="Куда выгрузить план построчно.")
        parser.add_argument("--min-share", type=float, default=MIN_SHARE)
        parser.add_argument("--min-leaf", type=int, default=MIN_LEAF_PRODUCTS)
        parser.add_argument("--min-home-share", type=float, default=MIN_HOME_SHARE)

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])

        plan = build_plan(
            min_share=options["min_share"],
            min_leaf=options["min_leaf"],
            min_home_share=options["min_home_share"],
        )
        text = self._render(plan)
        self.stdout.write(text)

        if options["markdown"]:
            path = Path(options["markdown"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Отчёт: {path}"))
        if options["csv"]:
            self._csv(plan, Path(options["csv"]))

        if not plan.moves:
            self.stdout.write(self.style.SUCCESS("\nПереносить нечего."))
            return
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit.")
            )
            return
        self._commit(plan)

    # ------------------------------------------------------------------ #
    def _render(self, plan) -> str:
        lines = [
            "# Перенос застрявших товаров в наличии",
            "",
            f"В пуле (опубликованы, в наличии, вне видимого дерева): **{plan.pool_size}**.",
            f"К переносу: **{len(plan.moves)}**. "
            f"На сверку глазами: {len(plan.needs_review)}. "
            f"Без решения: {sum(n for _s, _n, n, _r in plan.unresolved)} "
            f"в {len(plan.unresolved)} типах. Без `tool_type`: {len(plan.no_type)}.",
            "",
        ]
        if plan.moves:
            lines += [
                "## Куда переносим",
                "",
                "| Лист-получатель | Товаров | Обоснование |",
                "| -- | -- | -- |",
            ]
            for moves in sorted(plan.by_target.values(), key=lambda m: -len(m)):
                target = moves[0].target
                types = ", ".join(sorted({m.tool_type_name for m in moves}))
                lines.append(
                    f"| {target.name} (`{target.slug}`) | {len(moves)} | {types}: "
                    f"{moves[0].share:.0%} живых товаров типа уже здесь |"
                )
            lines += [
                "",
                "## Построчно",
                "",
                "| id | Товар | Остаток | Откуда | Куда | Тип |",
                "| -- | -- | -- | -- | -- | -- |",
            ]
            for move in sorted(plan.moves, key=lambda m: -m.product.stock_quantity):
                product = move.product
                source = product.category.name if product.category else "—"
                lines.append(
                    f"| {product.id} | {product.name} | {product.stock_quantity:g} | "
                    f"{source} | {move.target.name} | {move.tool_type_name} |"
                )
        if plan.needs_review:
            lines += [
                "",
                "## На сверку глазами — тип в листе чужой",
                "",
                "Правило «где тип преобладает» наследует ошибки существующего дерева: если",
                "несколько товаров по недосмотру лежат в чужом листе, оно уверенно отправит",
                "туда весь тип. Здесь тип занимает меньше пятой части листа-получателя —",
                "автоматически такие товары не едут.",
                "",
                "| Тип | Товаров | Предложенный лист | Занимает листа | Чем лист занят сейчас |",
                "| -- | -- | -- | -- | -- |",
            ]
            seen = set()
            for move in sorted(plan.needs_review, key=lambda m: -m.leaf_count):
                key = (move.tool_type, move.target.id)
                if key in seen:
                    continue
                seen.add(key)
                count = sum(1 for m in plan.needs_review if (m.tool_type, m.target.id) == key)
                main_name, main_count = move.leaf_main_type
                lines.append(
                    f"| {move.tool_type_name} | {count} | {move.target.name} "
                    f"(`{move.target.slug}`) | {move.home_share:.0%} | "
                    f"{main_name} ({main_count}) |"
                )
        if plan.unresolved:
            lines += [
                "",
                "## Без решения — лист не выводится",
                "",
                "| Тип | Товаров | Почему |",
                "| -- | -- | -- |",
            ]
            for _slug, name, count, reason in sorted(plan.unresolved, key=lambda r: -r[2]):
                lines.append(f"| {name} | {count} | {reason} |")
        if plan.no_type:
            lines += [
                "",
                "## Без `tool_type` — решение владельца",
                "",
                "Тип ради переноса не подставляем: он определяет и фильтры, и панель навигации.",
                "",
                "| id | Товар | Остаток | Категория |",
                "| -- | -- | -- | -- |",
            ]
            for product in plan.no_type:
                source = product.category.name if product.category else "—"
                lines.append(
                    f"| {product.id} | {product.name} | {product.stock_quantity:g} | {source} |"
                )
        return "\n".join(lines)

    def _csv(self, plan, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["id", "code_1c", "товар", "остаток", "откуда", "куда", "тип", "обоснование"]
            )
            for move in plan.moves:
                product = move.product
                writer.writerow(
                    [
                        product.id,
                        product.code_1c or "",
                        product.name,
                        product.stock_quantity,
                        product.category.name if product.category else "",
                        move.target.name,
                        move.tool_type_name,
                        move.evidence,
                    ]
                )
        self.stdout.write(self.style.SUCCESS(f"CSV: {path}"))

    # ------------------------------------------------------------------ #
    def _commit(self, plan):
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        path = backup_dir / f"relocate-stranded-{timezone.now():%Y%m%d-%H%M%S}.json"

        snapshot = [
            {
                "id": move.product.id,
                "category_id": move.product.category_id,
                "category_is_manual": move.product.category_is_manual,
            }
            for move in plan.moves
        ]
        moved_ids = []
        with transaction.atomic():
            for target_id, moves in plan.by_target.items():
                ids = [m.product.id for m in moves]
                # category_is_manual=True обязателен: без него следующий прогон
                # автокатегоризации утащит товар обратно в мёртвый корень.
                Product.objects.filter(id__in=ids).update(
                    category_id=target_id, category_is_manual=True
                )
                moved_ids += ids
            path.write_text(
                json.dumps({"products": snapshot}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # bulk update не шлёт post_save, поэтому кэши дерева и фасетов сами не
            # сбросятся — зовём явно, иначе витрина ещё TTL показывает старое дерево.
            transaction.on_commit(invalidate_category_tree_cache)
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(lambda ids=tuple(moved_ids): self._emit(ids))
        self.stdout.write(
            self.style.SUCCESS(f"\nCOMMIT: перенесено {len(moved_ids)}. Снимок отката: {path}")
        )

    @staticmethod
    def _emit(ids):
        for product_id in ids:
            product_updated.send(
                sender=Product,
                product_id=product_id,
                source=EventSource.SYSTEM,
                changed_fields=["category"],
            )

    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Снимок не найден: {file_path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CommandError(f"Битый JSON: {exc}") from exc
        rows = data.get("products", [])
        with transaction.atomic():
            for row in rows:
                Product.objects.filter(id=row["id"]).update(
                    category_id=row["category_id"],
                    category_is_manual=row["category_is_manual"],
                )
            transaction.on_commit(invalidate_category_tree_cache)
            transaction.on_commit(invalidate_facets_cache)
        self.stdout.write(self.style.SUCCESS(f"ROLLBACK: возвращено товаров {len(rows)}."))
