"""Аналитический тулкит для разбора 1С-подгруппы (issue: характеризация каталога).

Детерминированный измеритель для скилла ``characterize-subgroup``: считает состав
подгруппы, проверяет кандидаты-сплиты (с долей ложных) и покрытие атрибутов —
ровно те метрики, по которым вручную разбирались Буры/Коронки/Свёрла и т.д.
Read-only, работает на ``data/catalog_fixed.json`` (исходные имена 1С).

Рабочий цикл: агент пишет spec → гоняет команду → правит spec до нужных метрик
(0 ложных в сплитах, высокое покрытие) → переносит правила в
``data/tool_type_rules.json`` и ``data/attribute_rules.json``.

    ./manage.py analyze_subgroup "Буры"                     # только состав
    ./manage.py analyze_subgroup "Буры" --spec /tmp/bury.json --examples 15

Формат spec (JSON)::

    {
      "core_words": ["бур", "буры", "яябур"],
      "splits": {
        "nabory-burov": ["набор буров"],
        "osnastka-burov": ["удлинитель для бура", "адаптер"]
      },
      "attributes": {
        "diameter":   {"kind": "number", "regex": ["(?:^|\\\\s)(\\\\d{1,2})\\\\s*[хx*]\\\\s*\\\\d"]},
        "shank_type": {"kind": "select", "options": {"sds-plus": ["sds-plus", "sds+"]}}
      }
    }
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.ingest import load_json
from apps.catalog.tool_type import normalize


def names_for_subgroup(subgroup: str) -> list[str]:
    """Имена товаров 1С-подгруппы (по ``source_group`` листа дерева каталога)."""
    data = load_json("catalog_fixed.json")
    out: list[str] = []

    def walk(node, parent: str = "") -> None:
        if isinstance(node, list):
            for n in node:
                walk(n, parent)
            return
        children = node.get("children")
        if children:
            walk(children, node.get("name", ""))
        elif (node.get("source_group", "") or parent) == subgroup:
            out.append(node.get("name", ""))

    walk(data)
    return out


def _num_hit(patterns: list[re.Pattern], name: str):
    for pat in patterns:
        m = pat.search(name)
        if m:
            return m.group(1) if m.groups() else m.group(0)
    return None


def _sel_hit(options: dict[str, list[str]], name: str):
    for value, keywords in options.items():
        if any(normalize(k) in name for k in keywords):
            return value
    return None


class Command(BaseCommand):
    help = "Анализ 1С-подгруппы: состав, кандидаты-сплиты (доля ложных), покрытие атрибутов."

    def add_arguments(self, parser):
        parser.add_argument("subgroup", help="Имя 1С-подгруппы (source_group), напр. «Буры»")
        parser.add_argument("--spec", default=None, help="JSON-спека сплитов/атрибутов")
        parser.add_argument("--examples", type=int, default=10, help="Сколько примеров-промахов")

    def handle(self, *args, **opts):
        names = names_for_subgroup(opts["subgroup"])
        low = [normalize(n) for n in names]
        total = len(low)
        if total == 0:
            raise CommandError(
                f"Подгруппа {opts['subgroup']!r} не найдена в catalog_fixed.json "
                f"(проверьте точное имя source_group)."
            )
        write = self.stdout.write
        write(f"\nПодгруппа «{opts['subgroup']}»: {total} товаров")

        # 1) Состав — частоты первых слов (видны подтипы/аксессуары).
        first = Counter(n.split()[0] for n in low if n.split())
        write("\n--- состав (первое слово, топ-15) ---")
        for word, count in first.most_common(15):
            write(f"  {count:5}  {word}")

        if not opts["spec"]:
            write("\n(spec не передан — только состав. Добавьте --spec для сплитов/покрытия.)")
            return

        spec = json.loads(Path(opts["spec"]).read_text(encoding="utf-8"))
        core_words = {normalize(w) for w in spec.get("core_words", [])}
        splits = spec.get("splits", {})
        n_ex = opts["examples"]

        def split_of(name: str):
            for slug, keywords in splits.items():
                if any(normalize(k) in name for k in keywords):
                    return slug
            return None

        def is_core(name: str) -> bool:
            head = name.split()[0].lstrip("я") if name.split() else ""
            return head in core_words

        # 2) Сплиты — распределение + доля ложных (целевой тип ушёл в сплит).
        if splits:
            dist = Counter(split_of(n) or "CORE" for n in low)
            write("\n--- сплит подтипов ---")
            for slug, count in dist.most_common():
                write(f"  {count:5}  {slug}")
            false = [n for n in low if split_of(n) and is_core(n)]
            tag = "OK" if not false else "← проверьте: подтип (ок) или аксессуар (уточнить ключ)"
            write(f"  с core-первым-словом в сплите: {len(false)}  {tag}")
            for name in false[:n_ex]:
                write(f"      {name[:70]}  -> {split_of(name)}")

        # 3) Покрытие атрибутов — на CORE-товарах (вне сплитов).
        core = [n for n in low if split_of(n) is None]
        attrs = spec.get("attributes", {})
        if attrs:
            write(f"\n--- покрытие атрибутов (на {len(core)} CORE-товарах) ---")
        for slug, rule in attrs.items():
            if rule.get("kind") == "number":
                patterns = [re.compile(p) for p in rule.get("regex", [])]
                values = [_num_hit(patterns, n) for n in core]
            else:
                options = rule.get("options", {})
                values = [_sel_hit(options, n) for n in core]
            hits = sum(1 for v in values if v is not None)
            pct = 100 * hits // max(len(core), 1)
            write(f"\n  {slug}: {hits}/{len(core)} = {pct}%")
            for value, count in Counter(v for v in values if v is not None).most_common(6):
                write(f"      {count:5}  {value}")
            for name, value in zip(core, values, strict=True):
                if value is None and n_ex > 0:
                    write(f"      нет матча: {name[:64]}")
                    n_ex -= 1
            n_ex = opts["examples"]
