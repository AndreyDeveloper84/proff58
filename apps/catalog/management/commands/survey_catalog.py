"""Обзор всего каталога по 1С-подгруппам — приоритизация характеризации.

Read-only. Для каждой подгруппы (``source_group``) считает размер, доминирующий
тип (первое слово), долю аксессуаров и грубые сигналы извлекаемости: размеры
(Ø/мм), хвостовик (SDS), мощность (Вт/В). Сортировка по размеру — видно, какую
подгруппу брать следующей (много товаров + регулярные спеки → высокий приоритет).

Используется со скиллом ``characterize-subgroup`` как стартовый обзор. Сами
правила потом расставляются покатегорийно (см. ``analyze_subgroup``).

    ./manage.py survey_catalog
    ./manage.py survey_catalog --min 50 --top 40
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from apps.catalog.ingest import load_json
from apps.catalog.tool_type import normalize

# Грубые сигналы извлекаемости (по нормализованному имени).
_ACCESSORY = re.compile(
    r"адаптер|адептер|переходник|удлинитель|держател|державк|оправк|набор|комплект"
)
_DIMENSION = re.compile(r"\d{1,3}\s*[хx*]\s*\d|\d{1,3}\s*мм")
_SHANK = re.compile(r"sds|хвостовик|шестигран")
_POWER = re.compile(r"\d+\s*вт|\bв\b")


def subgroup_names() -> dict[str, list[str]]:
    """{source_group: [имена товаров]} из дерева catalog_fixed.json."""
    data = load_json("catalog_fixed.json")
    groups: dict[str, list[str]] = defaultdict(list)

    def walk(node, parent: str = "") -> None:
        if isinstance(node, list):
            for n in node:
                walk(n, parent)
            return
        children = node.get("children")
        if children:
            walk(children, node.get("name", ""))
        else:
            sg = node.get("source_group", "") or parent
            if sg:
                groups[sg].append(node.get("name", ""))

    walk(data)
    return groups


def _pct(part: int, whole: int) -> int:
    return 100 * part // whole if whole else 0


class Command(BaseCommand):
    help = "Обзор каталога по 1С-подгруппам с сигналами извлекаемости (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--min", type=int, default=20, help="Минимум товаров в подгруппе")
        parser.add_argument("--top", type=int, default=80, help="Сколько строк показать")

    def handle(self, *args, **opts):
        groups = subgroup_names()
        rows = []
        for subgroup, names in groups.items():
            n = len(names)
            if n < opts["min"]:
                continue
            low = [normalize(x) for x in names]
            first = Counter(x.split()[0].lstrip("я") for x in low if x.split())
            top_word, top_count = first.most_common(1)[0] if first else ("—", 0)
            rows.append(
                {
                    "n": n,
                    "subgroup": subgroup,
                    "type": top_word,
                    "type_pct": _pct(top_count, n),
                    "acc": _pct(sum(1 for x in low if _ACCESSORY.search(x)), n),
                    "dim": _pct(sum(1 for x in low if _DIMENSION.search(x)), n),
                    "sds": _pct(sum(1 for x in low if _SHANK.search(x)), n),
                    "pwr": _pct(sum(1 for x in low if _POWER.search(x)), n),
                }
            )
        rows.sort(key=lambda r: r["n"], reverse=True)

        write = self.stdout.write
        write(f"\nПодгрупп с ≥{opts['min']} товаров: {len(rows)} (из {len(groups)} всего)\n")
        write(
            f"{'товаров':>7}  {'тип (доля)':<24} {'акс%':>4} {'разм%':>5} {'sds%':>4} {'Вт/В%':>5}  подгруппа"
        )
        write("-" * 92)
        for r in rows[: opts["top"]]:
            type_col = f"{r['type'][:16]} {r['type_pct']}%"
            write(
                f"{r['n']:>7}  {type_col:<24} {r['acc']:>4} {r['dim']:>5} {r['sds']:>4} "
                f"{r['pwr']:>5}  {r['subgroup']}"
            )
        write(
            f"\nИтого товаров в показанных подгруппах: {sum(r['n'] for r in rows[: opts['top']])}"
        )
        write(
            "\nЧитать: высокий «разм%»/«sds%»/«Вт/В%» → регулярные спеки (легко); "
            "высокий «акс%» → много аксессуаров (нужен сплит)."
        )
