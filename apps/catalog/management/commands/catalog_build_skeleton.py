"""Построить ПОЛНЫЙ скелет v2-дерева (все разделы) и вывести на фронт — без товаров.

В отличие от ``catalog_build_section`` (строит ОДИН раздел скрыто + расселяет товары),
эта команда создаёт СТРУКТУРУ всех 13 разделов из словарей (раздел → подкатегории →
подтипы) сразу и ВИДИМОЙ (is_active=True, on_site=True) — чтобы целевое дерево было на
витрине, пусть и с пустыми категориями. Товары НЕ двигает. Наполняем потом
(``catalog_build_section`` по разделам).

    ./manage.py catalog_build_skeleton                 # dry-run (что создастся)
    ./manage.py catalog_build_skeleton --commit         # создать (видимо)
    ./manage.py catalog_build_skeleton --hidden --commit # создать скрыто (если надо)
    ./manage.py catalog_build_skeleton --section krepezh --commit  # только один раздел
    ./manage.py catalog_build_skeleton --rollback var/restructure/skeleton-<ts>.json

Идемпотентно: существующие узлы (по slug/имени) переиспользуются; видимость
выставляется по флагу. Узлы-листья с товарами/детьми при откате НЕ удаляются.

ВАЖНО: команда НЕ трогает легаси-дерево. Пока товары раздела не мигрировали
(``catalog_build_section`` + swap), на витрине будут видны И пустые v2-узлы, И легаси
с товарами (временное сосуществование). Легаси гасим по разделам по мере наполнения.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Category
from apps.catalog.semantic import SECTION_RULES, load_rules, translit_slug


class Command(BaseCommand):
    help = "Построить полный скелет v2-дерева (все разделы) видимым, без переноса товаров."

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTION_RULES), help="Только один раздел.")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument(
            "--hidden",
            action="store_true",
            help="Создавать скрытыми (is_active=False, on_site=False). По умолчанию — видимо.",
        )
        parser.add_argument("--rollback", metavar="FILE")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        sections = [options["section"]] if options["section"] else list(SECTION_RULES)
        visible = not options["hidden"]

        plan = []  # [(section_name, section_slug, [(subcat, [subtype,...]),...])]
        for s in sections:
            doc, compiled = load_rules(SECTION_RULES[s])
            subcats, subtypes, seen = [], {}, set()
            for subcat, subtype, *_ in compiled:
                if subcat not in seen:
                    seen.add(subcat)
                    subcats.append(subcat)
                    subtypes[subcat] = []
                if subtype and subtype not in subtypes[subcat]:
                    subtypes[subcat].append(subtype)
            plan.append((doc["section"], doc["section_slug"], subcats, subtypes))

        self._report(plan, visible)
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не создано. Применить — --commit.")
            )
            return
        self._commit(plan, visible)

    # ------------------------------------------------------------------ #
    def _report(self, plan, visible):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING("\n=== Скелет v2-дерева (dry-run) ==="))
        w(f"Видимость новых узлов: {'ВИДИМО (on_site=True)' if visible else 'скрыто'}")
        total = 0
        for name, slug, subcats, subtypes in plan:
            nleaf = len(subcats) + sum(len(subtypes[sc]) for sc in subcats)
            total += nleaf + 1
            exists = Category.objects.filter(slug=slug).exists()
            w(f"  ■ {name} (slug={slug}){'' if exists else '  [корень новый]'} — узлов {nleaf + 1}")
        w(self.style.SUCCESS(f"\nИТОГО узлов в скелете: ~{total} (создаются недостающие)."))

    def _unique_slug(self, name: str, parent: Category | None) -> str:
        base = translit_slug(name)
        if not Category.objects.filter(slug=base).exists():
            return base
        prefix = parent.slug if parent else "v2"
        return f"{prefix}-{base}"

    def _ensure(self, parent, name, order, visible, created, slug=None):
        if parent is None:
            node = Category.objects.filter(slug=slug).first() if slug else None
            node = node or Category.objects.filter(name=name, depth=1).first()
        else:
            node = parent.get_children().filter(name=name).first()
        if node:
            if node.is_active != visible or node.on_site != visible:
                node.is_active = visible
                node.on_site = visible
                node.save(update_fields=["is_active", "on_site"])
            return node
        if parent is None:
            node = Category.add_root(
                name=name,
                slug=slug or self._unique_slug(name, None),
                is_active=visible,
                on_site=visible,
            )
        else:
            node = parent.add_child(
                name=name,
                slug=self._unique_slug(name, parent),
                sort_order=order,
                is_active=visible,
                on_site=visible,
            )
        created.append(node.pk)
        return node

    def _commit(self, plan, visible):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"skeleton-{ts}.json"
        created: list[int] = []
        with transaction.atomic():
            for name, slug, subcats, subtypes in plan:
                root = self._ensure(None, name, 0, visible, created, slug=slug)
                for i, sc in enumerate(subcats):
                    sc_node = self._ensure(root, sc, i, visible, created)
                    for j, st in enumerate(subtypes[sc]):
                        self._ensure(sc_node, st, j, visible, created)
            backup_path.write_text(json.dumps({"created": created}, ensure_ascii=False))
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: создано узлов {len(created)} "
                f"({'видимо' if visible else 'скрыто'}). Снимок отката: {backup_path}"
            )
        )

    # ------------------------------------------------------------------ #
    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Снимок не найден: {file_path}")
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise CommandError(f"Битый JSON: {exc}") from exc
        ids = data.get("created", [])
        deleted = 0
        with transaction.atomic():
            nodes = Category.objects.filter(id__in=ids)
            for node in sorted(nodes, key=lambda c: c.depth, reverse=True):
                if not node.get_children().exists() and not node.products.exists():
                    node.delete()
                    deleted += 1
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK: удалено пустых узлов {deleted} из {len(ids)} " "(непустые оставлены)."
            )
        )
