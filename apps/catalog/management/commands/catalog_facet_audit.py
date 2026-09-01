"""Аудит фильтров каталога: круг «фасет → фильтр», сайдбары листьев, привязки, данные.

Только чтение — команда ничего не пишет и безопасна на боевом стенде.

    ./manage.py catalog_facet_audit                     # всё, текстом
    ./manage.py catalog_facet_audit --circle            # только круг фасет→фильтр
    ./manage.py catalog_facet_audit --markdown docs/catalog/facets-audit.md
    ./manage.py catalog_facet_audit --outside-csv var/outside-tree.csv

Круг «фасет → фильтр» — регрессионный замер: если счётчик в сайдбаре разошёлся с
числом товаров, которое отдаёт фильтр по тому же значению, команда завершается
кодом 1. Молча отчитаться о расхождении и вернуть 0 — значит сделать замер
бесполезным; подавить можно явным ``--allow-drift``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.facet_audit import (
    audit_bindings,
    audit_fill,
    audit_sidebars,
    check_circle,
    visible_categories,
    visible_leaves,
)
from apps.catalog.filters import visible_products


class Command(BaseCommand):
    help = "Аудит фильтров и заполненности каталога (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--circle", action="store_true", help="Круг «фасет → фильтр».")
        parser.add_argument("--sidebar", action="store_true", help="Сайдбар по листьям.")
        parser.add_argument("--bindings", action="store_true", help="Привязки и атрибуты.")
        parser.add_argument("--fill", action="store_true", help="Заполненность каталога.")
        parser.add_argument(
            "--values",
            type=int,
            default=3,
            help="Сколько значений каждого фасета сверять в круге (по умолчанию 3).",
        )
        parser.add_argument("--allow-drift", action="store_true", help="Не падать на расхождении.")
        parser.add_argument("--markdown", metavar="FILE", help="Куда сложить отчёт в markdown.")
        parser.add_argument(
            "--outside-csv",
            metavar="FILE",
            help="Куда выгрузить товары в наличии вне видимого дерева.",
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        chosen = {k: options[k] for k in ("circle", "sidebar", "bindings", "fill")}
        if not any(chosen.values()):
            chosen = dict.fromkeys(chosen, True)  # без флагов — полный отчёт

        visible = visible_categories()
        leaves = visible_leaves(visible)
        out: list[str] = [
            "# Аудит фильтров каталога",
            "",
            f"Видимых категорий: **{len(visible)}**, из них листьев: **{len(leaves)}**.",
            "",
        ]
        drift = False

        if chosen["bindings"]:
            out += self._bindings(visible)
        if chosen["sidebar"]:
            out += self._sidebar(leaves)
        if chosen["fill"]:
            out += self._fill(visible, options["outside_csv"])
        if chosen["circle"]:
            block, drift = self._circle(visible, options["values"])
            out += block

        text = "\n".join(out)
        self.stdout.write(text)
        if options["markdown"]:
            path = Path(options["markdown"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"\nОтчёт: {path}"))
        if drift and not options["allow_drift"]:
            raise CommandError("Круг «фасет → фильтр» разошёлся — см. таблицу выше.")

    # ------------------------------------------------------------------ #
    def _bindings(self, visible) -> list[str]:
        rep = audit_bindings(visible)
        lines = [
            "## Привязки характеристик",
            "",
            f"Всего привязок `CategoryAttribute`: **{rep.total}**, "
            f"из них на категориях вне витрины: **{len(rep.dead)}**.",
            "",
            "Глубина живых привязок: "
            + ", ".join(f"{d} — {n}" for d, n in rep.depth_histogram.items())
            + ".",
            "",
        ]
        if rep.dead:
            lines += ["| Категория | slug | Глубина | Атрибут |", "| -- | -- | -- | -- |"]
            for ca in sorted(rep.dead, key=lambda ca: (ca.category.path, ca.attribute.slug)):
                lines.append(
                    f"| {ca.category.name} | `{ca.category.slug}` | "
                    f"{ca.category.depth} | `{ca.attribute.slug}` |"
                )
            lines.append("")
        lines += [
            "Атрибуты, встречающиеся ТОЛЬКО на невидимых категориях (фасет потерян): "
            + (", ".join(f"`{s}`" for s in rep.dead_only) if rep.dead_only else "нет")
            + ".",
            "",
        ]
        if rep.orphan_attributes:
            lines += [
                f"Атрибутов без единой привязки: **{len(rep.orphan_attributes)}** — "
                + ", ".join(f"`{a.slug}`" for a in rep.orphan_attributes)
                + ".",
                "",
            ]
        return lines

    # ------------------------------------------------------------------ #
    def _sidebar(self, leaves) -> list[str]:
        reports = audit_sidebars(leaves)
        empty = [r for r in reports if not r.has_sidebar]
        no_attr = [r for r in reports if not r.usable_facets]
        fixable = [r for r in reports if r.unbound_axes]
        lines = [
            "## Сайдбар по листьям",
            "",
            f"Листьев без единого способа сузить выдачу (ни фасета, ни панели типов): "
            f"**{len(empty)}** — {sum(r.total for r in empty)} товаров, "
            f"{sum(r.in_stock for r in empty)} в наличии.",
            "",
            f"Листьев без рабочего атрибутного фасета (панель типов при этом может быть): "
            f"**{len(no_attr)}** — {sum(r.total for r in no_attr)} товаров, "
            f"{sum(r.in_stock for r in no_attr)} в наличии.",
            "",
            f"Листьев, где сайдбар чинится привязкой (значения есть, фасета нет): "
            f"**{len(fixable)}**.",
            "",
            "### По разделам",
            "",
            "| Раздел | Листьев | Без сайдбара | Товаров | В наличии |",
            "| -- | -- | -- | -- | -- |",
        ]
        sections: dict[str, list[int]] = {}
        for r in reports:
            acc = sections.setdefault(r.section, [0, 0, 0, 0])
            acc[0] += 1
            acc[1] += 0 if r.has_sidebar else 1
            acc[2] += r.total
            acc[3] += r.in_stock
        for name, acc in sorted(sections.items(), key=lambda kv: -kv[1][3]):
            lines.append(f"| {name} | {acc[0]} | {acc[1]} | {acc[2]} | {acc[3]} |")
        lines += [
            "",
            "### Листья без сайдбара",
            "",
            "| id | Категория | Товаров | В наличии | Чего не хватает |",
            "| -- | -- | -- | -- | -- |",
        ]
        for r in sorted(empty, key=lambda r: -r.in_stock):
            need = (
                ", ".join(f"`{s}` ({v} знач./{n} тов.)" for s, v, n in r.unbound_axes[:4])
                if r.unbound_axes
                else "характеристики не заполнены"
            )
            lines.append(
                f"| {r.category.id} | {r.category.name} | {r.total} | {r.in_stock} | {need} |"
            )
        if fixable:
            lines += [
                "",
                "### Листья, где ось заполнена, но фасета нет",
                "",
                "| id | Категория | В наличии | Оси |",
                "| -- | -- | -- | -- |",
            ]
            for r in sorted(fixable, key=lambda r: -r.in_stock):
                axes = ", ".join(f"`{s}` ({v} знач./{n} тов.)" for s, v, n in r.unbound_axes)
                lines.append(f"| {r.category.id} | {r.category.name} | {r.in_stock} | {axes} |")
        lines.append("")
        return lines

    # ------------------------------------------------------------------ #
    def _fill(self, visible, outside_csv) -> list[str]:
        rep = audit_fill(visible)
        lines = [
            "## Заполненность каталога",
            "",
            "| Показатель | Значение |",
            "| -- | -- |",
            f"| Опубликованных и активных | {rep.published} |",
            f"| В видимом дереве | {rep.in_tree} |",
            f"| Вне видимого дерева | {rep.outside} (в наличии {rep.outside_in_stock}) |",
            f"| В наличии | {rep.in_stock} |",
            f"| — без фото | {rep.no_photo} |",
            f"| — без характеристик | {rep.no_attrs} |",
            f"| — без tool_type | {rep.no_tool_type} |",
            f"| — с пустым брендом | {rep.no_brand} |",
            "",
            "### Куда сложены товары вне витрины",
            "",
            "| id | Категория | Товаров |",
            "| -- | -- | -- |",
        ]
        for cid, name, n in rep.outside_top:
            lines.append(f"| {cid} | {name} | {n} |")
        lines.append("")
        if outside_csv:
            path = Path(outside_csv)
            path.parent.mkdir(parents=True, exist_ok=True)
            vis_ids = {c.id for c in visible}
            rows = (
                visible_products()
                .exclude(category_id__in=vis_ids)
                .filter(stock_quantity__gt=0)
                .select_related("category")
                .order_by("-stock_quantity", "name")
            )
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    ["id", "code_1c", "article", "name", "brand", "остаток", "категория"]
                )
                for p in rows:
                    writer.writerow(
                        [
                            p.id,
                            p.code_1c or "",
                            p.article or "",
                            p.name,
                            p.brand,
                            p.stock_quantity,
                            p.category.name if p.category else "",
                        ]
                    )
            lines += [f"Полный список позиций в наличии вне дерева: `{path}`.", ""]
        return lines

    # ------------------------------------------------------------------ #
    def _circle(self, visible, values_per_facet) -> tuple[list[str], bool]:
        res = check_circle(visible, values_per_facet=values_per_facet)
        lines = [
            "## Круг «фасет → фильтр»",
            "",
            f"Сверено пар «значение фасета → фильтр»: **{res.pairs}** "
            f"в {res.categories} категориях. Расхождений: **{len(res.drift)}**.",
            "",
        ]
        if res.drift:
            lines += [
                "| Категория | Атрибут | Значение | Фасет | Фильтр |",
                "| -- | -- | -- | -- | -- |",
            ]
            for cat_slug, attr_slug, value, expected, actual in res.drift:
                lines.append(f"| `{cat_slug}` | `{attr_slug}` | {value} | {expected} | {actual} |")
            lines.append("")
        return lines, bool(res.drift)
