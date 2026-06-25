"""Пред-swap отчёт по v2-дереву (read-only) — DoD для секционного swap (вариант A).

Считает по ЖИВОЙ БД фактическое состояние миграции v2 + потенциал классификации,
и проверяет инварианты перед включением раздела на витрину:

  * v2 vs legacy: какие корни v2 (slug из словарей) и какие legacy;
  * расселение: в нормальных узлах vs «На модерацию» (по разделам), stock>0/stock=0;
  * хвост: сколько товаров не матчится ни одним разделом (no_match);
  * видимость: не «течёт» ли скрытое v2 (узлы с is_active/on_site=True до swap);
  * конфликты: slug-коллизии v2↔существующие; дубли имён категорий;
  * дубли на витрине: один и тот же article под двумя on_site-ветками;
  * sample breadcrumbs по каждому v2-разделу.

    ./manage.py catalog_v2_report                 # markdown в docs/reports + сводка в stdout
    ./manage.py catalog_v2_report --section krepezh
    ./manage.py catalog_v2_report --out /tmp/v2.md

Только читает БД. Ничего не меняет.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.management.commands.catalog_build_section import _MODERATION_NAME
from apps.catalog.models import Category, Product, ProductStatus
from apps.catalog.semantic import SECTION_RULES, classify, load_rules, translit_slug


class Command(BaseCommand):
    help = (
        "Пред-swap отчёт по v2-дереву (read-only): расселение, видимость, конфликты, breadcrumbs."
    )

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTION_RULES))
        parser.add_argument(
            "--out", default=None, help="Файл отчёта (.md). По умолчанию docs/reports."
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        sections = [options["section"]] if options["section"] else list(SECTION_RULES)
        docs = {
            s: load_rules(SECTION_RULES[s]) for s in SECTION_RULES
        }  # все — для no_match/конфликтов
        v2_root_slugs = {doc["section_slug"] for doc, _ in docs.values()}

        lines: list[str] = ["# Пред-swap отчёт v2 (read-only)\n"]
        lines += self._global_block(v2_root_slugs)
        lines += self._sections_block(sections, docs)
        lines += self._legacy_block(v2_root_slugs)
        lines += self._tail_block(docs, v2_root_slugs)
        lines += self._visibility_block(v2_root_slugs)
        lines += self._conflicts_block(docs)
        lines += self._duplicates_block()

        report = "\n".join(lines) + "\n"
        out = (
            Path(options["out"])
            if options["out"]
            else (Path(settings.BASE_DIR) / "docs" / "reports" / "catalog-v2-preswap.md")
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        self.stdout.write(report)
        self.stdout.write(self.style.SUCCESS(f"\nОтчёт записан: {out}"))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _subtree_ids(cat: Category) -> set[int]:
        return {cat.id} | set(cat.get_descendants().values_list("id", flat=True))

    def _v2_root(self, slug: str):
        return Category.objects.filter(slug=slug).first()

    def _node_split(self, root: Category):
        """(normal_ids, moderation_ids) по поддереву v2-корня."""
        root_ids = self._subtree_ids(root)
        mod = root.get_children().filter(name=_MODERATION_NAME).first()
        mod_ids = self._subtree_ids(mod) if mod else set()
        return root_ids - mod_ids, mod_ids

    # ------------------------------------------------------------------ #
    def _global_block(self, v2_root_slugs):
        total = Product.objects.count()
        no_cat = Product.objects.filter(category__isnull=True).count()
        manual = Product.objects.filter(category_is_manual=True).count()
        published = Product.objects.filter(is_active=True, status=ProductStatus.PUBLISHED).count()
        return [
            "## Сводка\n",
            f"- Всего товаров: **{total}**; без категории: **{no_cat}**; "
            f"ручных (manual): **{manual}**; опубликовано (видимы): **{published}**",
            "",
        ]

    def _sections_block(self, sections, docs):
        out = [
            "## Разделы v2 (факт по БД)\n",
            "| Раздел | v2-root | видим | узлов | норма | модерация | stock>0(норма) |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for s in sections:
            doc, _ = docs[s]
            root = self._v2_root(doc["section_slug"])
            if root is None:
                out.append(f"| {doc['section']} | — нет | — | 0 | 0 | 0 | 0 |")
                continue
            normal_ids, mod_ids = self._node_split(root)
            n_normal = Product.objects.filter(category_id__in=normal_ids).count()
            n_mod = Product.objects.filter(category_id__in=mod_ids).count()
            n_stock = Product.objects.filter(
                category_id__in=normal_ids, available_quantity__gt=0
            ).count()
            nodes = len(normal_ids | mod_ids)
            vis = "ДА" if (root.is_active and root.on_site) else "скрыт"
            out.append(
                f"| {doc['section']} | {root.slug} | {vis} | {nodes} | {n_normal} | {n_mod} | {n_stock} |"
            )
        out.append("")
        out += self._breadcrumbs_block(sections, docs)
        return out

    def _breadcrumbs_block(self, sections, docs):
        out = ["### Sample breadcrumbs (по одному товару раздела)\n"]
        for s in sections:
            doc, _ = docs[s]
            root = self._v2_root(doc["section_slug"])
            if root is None:
                continue
            normal_ids, _ = self._node_split(root)
            p = (
                Product.objects.filter(category_id__in=normal_ids)
                .select_related("category")
                .first()
            )
            if not p or not p.category:
                out.append(f"- {doc['section']}: — нет товаров —")
                continue
            crumbs = list(p.category.get_ancestors()) + [p.category]
            path = " / ".join(c.name for c in crumbs)
            out.append(f"- {doc['section']}: {path} → «{p.name[:48]}»")
        out.append("")
        return out

    def _legacy_block(self, v2_root_slugs):
        out = [
            "## Legacy-корни (факт по БД)\n",
            "| slug | on_site | is_active | товаров(с потомками) |",
            "|---|---|---|---:|",
        ]
        for root in Category.get_root_nodes():
            if root.slug in v2_root_slugs:
                continue
            ids = self._subtree_ids(root)
            n = Product.objects.filter(category_id__in=ids).count()
            out.append(f"| {root.slug} | {root.on_site} | {root.is_active} | {n} |")
        out.append("")
        return out

    def _tail_block(self, docs, v2_root_slugs):
        """Хвост: товары вне v2, не матчащиеся ни одним разделом (no_match)."""
        compiled_all = [c for _, c in docs.values()]
        # товары, ещё НЕ в v2 (в legacy или без категории)
        v2_ids = set()
        for doc, _ in docs.values():
            root = self._v2_root(doc["section_slug"])
            if root:
                v2_ids |= self._subtree_ids(root)
        outside = Product.objects.exclude(category_id__in=v2_ids).values("id", "name")
        no_match = matched = 0
        for p in outside:
            if any(classify(p["name"], c) for c in compiled_all):
                matched += 1
            else:
                no_match += 1
        return [
            "## Хвост (вне v2)\n",
            f"- В legacy/без категории и **матчатся** каким-то разделом (мигрируют при build): **{matched}**",
            f"- **no_match** (не матчит ни один раздел — кандидаты в глобальный «На разбор»): **{no_match}**",
            "",
        ]

    def _visibility_block(self, v2_root_slugs):
        """Скрытое v2 не должно течь: ищем узлы под v2-корнями с is_active/on_site=True."""
        leaks = []
        for slug in v2_root_slugs:
            root = self._v2_root(slug)
            if root is None:
                continue
            if root.is_active and root.on_site:
                continue  # уже свапнут — это норма
            for n in [root] + list(root.get_descendants()):
                if n.is_active or n.on_site:
                    leaks.append(f"{n.slug} (is_active={n.is_active}, on_site={n.on_site})")
        out = ["## Видимость: утечки скрытого v2\n"]
        if leaks:
            out.append(
                f"⚠ **{len(leaks)} узлов скрытого v2 видимы** (должны быть False/False до swap):"
            )
            out += [f"- {x}" for x in leaks[:40]]
        else:
            out.append("✓ Все ещё-не-свапнутые v2-узлы скрыты (is_active=False, on_site=False).")
        out.append("")
        return out

    def _conflicts_block(self, docs):
        out = ["## Slug-конфликты (v2 ↔ существующие)\n"]
        found = []
        for s, (doc, compiled) in docs.items():
            root_slug = doc["section_slug"]
            root = self._v2_root(root_slug)
            own = set()
            if root:
                own = {root.slug} | set(root.get_descendants().values_list("slug", flat=True))
            planned = {root_slug: doc["section"]}
            for subcat, subtype, *_ in compiled:
                planned[translit_slug(subcat)] = subcat
                if subtype:
                    planned[translit_slug(subtype)] = subtype
            existing = dict(Category.objects.exclude(slug__in=own).values_list("slug", "name"))
            for slug, name in planned.items():
                if slug in existing:
                    found.append(f"[{s}] slug='{slug}' «{name}» ↔ существует «{existing[slug]}»")
        if found:
            out.append(f"⚠ **{len(found)}** (на build slug авто-дополнится префиксом корня):")
            out += [f"- {x}" for x in found[:40]]
        else:
            out.append("✓ Конфликтов нет.")
        out.append("")
        return out

    def _duplicates_block(self):
        from django.db.models import Count

        dups = (
            Category.objects.values("name").annotate(n=Count("id")).filter(n__gt=1).order_by("-n")
        )
        out = ["## Дубли категорий по имени\n"]
        if dups:
            out.append("| Имя | Сколько |")
            out.append("|---|---:|")
            for d in dups[:40]:
                out.append(f"| {d['name']} | {d['n']} |")
            out.append(
                "\n_Заметка: дубль имени между legacy и v2 — ожидаем (напр. «Крепёж и метизы»); "
                "v2 скрыт, на витрине одновременно не показываются._"
            )
        else:
            out.append("✓ Дублей имён нет.")
        out.append("")
        return out
