"""Семантическая классификация каталога по словарю (read-only, dry-run).

Классифицирует товары по СМЫСЛУ названия (а не по группам 1С) словарём
``data/product_type_rules.json``: раздел → подкатегория → [подтип] + confidence.
Источник имён — ``data/catalog_fixed.json`` (БД не требуется). Ничего не меняет:
только пишет отчёты в ``docs/reports/`` для ревью перед применением (E2/E3).

    ./manage.py catalog_semantic_classify                       # Оснастка по умолчанию
    ./manage.py catalog_semantic_classify --rules data/... --out docs/reports

Выход:
* ``catalog-classify-<slug>-summary.md`` — объёмы по подкат/подтипам (в наличии/всего),
  разбивка по confidence, хвост на доработку словаря;
* ``catalog-classify-<slug>-items.csv`` — per-item (раздел/подтип/confidence/совпадение);
* ``catalog-classify-<slug>-review.csv`` — только medium/low confidence (на модерацию).
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.semantic import classify, load_rules

GROUP_NODE = "1"


def _iter_products(tree: list[dict]):
    def walk(node: dict):
        if str(node.get("ProductGroup")) == GROUP_NODE:
            for ch in node.get("children") or []:
                yield from walk(ch)
        else:
            yield node

    for root in tree:
        yield from walk(root)


def _stock(node: dict) -> float:
    try:
        return float(node.get("stock") or 0)
    except (TypeError, ValueError):
        return 0.0


class Command(BaseCommand):
    help = "Семантическая классификация каталога по словарю (read-only, dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--rules", default="data/product_type_rules.json")
        parser.add_argument("--source", default="data/catalog_fixed.json")
        parser.add_argument(
            "--out", default=None, help="Каталог отчётов (по умолчанию docs/reports)."
        )

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        try:
            rules_doc, compiled = load_rules(options["rules"])
            tree = json.loads((base / options["source"]).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(f"Не прочитать вход: {exc}") from exc

        slug = rules_doc.get("section_slug", "section")
        section = rules_doc.get("section", slug)

        products = list(_iter_products(tree))
        rows = []  # per-item для CSV
        sub_cnt = defaultdict(lambda: [0, 0])  # (subcat,subtype) -> [in_stock, total]
        cat_cnt = defaultdict(lambda: [0, 0])  # subcat -> [in_stock, total]
        conf_cnt = defaultdict(lambda: [0, 0])  # confidence -> [in_stock, total]
        matched_in = matched_tot = 0

        for p in products:
            name = p.get("name", "")
            ist = 1 if _stock(p) > 0 else 0
            hit = classify(name, compiled)
            if hit is None:
                continue  # не этот раздел — не отчитываем как «пропуск»
            subcat, subtype, conf, kw = hit
            matched_in += ist
            matched_tot += 1
            sub_cnt[(subcat, subtype)][ist] += 1
            cat_cnt[subcat][ist] += 1
            conf_cnt[conf][ist] += 1
            rows.append(
                {
                    "external_id": p.get("external_id", ""),
                    "sku": p.get("sku", ""),
                    "name": name,
                    "stock": p.get("stock", "0"),
                    "subcat": subcat,
                    "subtype": subtype or "",
                    "confidence": conf,
                    "matched": kw,
                }
            )

        out_dir = Path(options["out"]) if options["out"] else base / "docs" / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._write_summary(
            out_dir / f"catalog-classify-{slug}-summary.md",
            section,
            len(products),
            matched_in,
            matched_tot,
            cat_cnt,
            sub_cnt,
            conf_cnt,
        )
        self._write_csv(out_dir / f"catalog-classify-{slug}-items.csv", rows)
        review = [r for r in rows if r["confidence"] in ("medium", "low")]
        self._write_csv(out_dir / f"catalog-classify-{slug}-review.csv", review)

        self.stdout.write(
            self.style.SUCCESS(
                f"Раздел «{section}»: классифицировано {matched_tot} (в наличии {matched_in}); "
                f"на модерацию {len(review)}. Отчёты: {out_dir}"
            )
        )

    def _write_summary(
        self, path, section, total_products, m_in, m_tot, cat_cnt, sub_cnt, conf_cnt
    ):
        L = []
        L.append(f"# Классификация: {section} (dry-run, read-only)\n")
        L.append(f"Всего товаров в дампе: {total_products}  ")
        L.append(f"Классифицировано в раздел: **{m_tot}** (в наличии **{m_in}**)\n")
        L.append("## Confidence\n")
        L.append("| Уровень | В наличии | Всего |")
        L.append("|---|---:|---:|")
        for c in ("high", "medium", "low"):
            v = conf_cnt.get(c, [0, 0])
            L.append(f"| {c} | {v[1]} | {v[0] + v[1]} |")
        L.append("\n## Подкатегории (в наличии / всего)\n")
        L.append("| Подкатегория | В нал. | Всего |")
        L.append("|---|---:|---:|")
        for sc, v in sorted(cat_cnt.items(), key=lambda kv: -kv[1][1]):
            L.append(f"| {sc} | {v[1]} | {v[0] + v[1]} |")
        L.append("\n## Подтипы 3-го уровня (в наличии / всего)\n")
        L.append("| Подкатегория → подтип | В нал. | Всего |")
        L.append("|---|---:|---:|")
        for (sc, st), v in sorted(sub_cnt.items(), key=lambda kv: (kv[0][0], -kv[1][1])):
            if st:
                L.append(f"| {sc} → {st} | {v[1]} | {v[0] + v[1]} |")
        L.append(
            "\n> Источник: `data/product_type_rules.json`. medium/low — в "
            "`*-review.csv` на модерацию. Данные не менялись (dry-run).\n"
        )
        path.write_text("\n".join(L), encoding="utf-8")

    def _write_csv(self, path, rows):
        cols = ["external_id", "sku", "name", "stock", "subcat", "subtype", "confidence", "matched"]
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
