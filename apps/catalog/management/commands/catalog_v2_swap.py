"""Секционный swap v2 ↔ legacy (вариант A) — ВКЛЮЧЕНИЕ раздела на витрину.

Запускать ТОЛЬКО после явного утверждения и зелёного `catalog_v2_report` по разделу.
Делает в одной транзакции:

  1. v2-корень раздела + все его узлы → видимы (is_active=True, on_site=True),
     КРОМЕ узла «На модерацию» (остаётся скрытым);
  2. указанные legacy-корни (--hide-legacy) → скрыты (is_active=False, on_site=False);
  3. снимок отката видимости (var/restructure/swap-<section>-<ts>.json);
  4. артефакт плана 301-redirect (legacy-категория → v2-корень) — CSV; реальных 301
     команда НЕ создаёт (модели redirect в проекте нет — Фаза 3).

    ./manage.py catalog_v2_swap --section krepezh --hide-legacy krepezh-i-metizy        # dry-run
    ./manage.py catalog_v2_swap --section krepezh --hide-legacy krepezh-i-metizy --commit
    ./manage.py catalog_v2_swap --rollback var/restructure/swap-krepezh-<ts>.json

GUARD: перед скрытием legacy-корня печатает, сколько товаров в нём останется (станут
не видны в дереве). С --force продолжает молча; без --force при непустом legacy и
--commit — требует подтверждения флагом.
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
from apps.catalog.management.commands.catalog_build_section import _MODERATION_NAME
from apps.catalog.models import Category, Product
from apps.catalog.semantic import SECTION_RULES, load_rules


class Command(BaseCommand):
    help = "Секционный swap v2↔legacy: включить v2-раздел на витрину, скрыть legacy (gated)."

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTION_RULES))
        parser.add_argument(
            "--hide-legacy",
            default="",
            help="Slug'и legacy-корней через запятую, которые скрыть при swap.",
        )
        parser.add_argument("--commit", action="store_true")
        parser.add_argument(
            "--force", action="store_true", help="Не требовать подтверждения guard."
        )
        parser.add_argument("--rollback", metavar="FILE")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        section = options["section"]
        if not section:
            raise CommandError("Укажите --section или --rollback FILE.")
        doc, _ = load_rules(SECTION_RULES[section])
        root = Category.objects.filter(slug=doc["section_slug"]).first()
        if root is None:
            raise CommandError(
                f"v2-корень (slug={doc['section_slug']}) не найден — сначала постройте раздел "
                "командой catalog_build_section."
            )

        legacy_slugs = [s.strip() for s in options["hide_legacy"].split(",") if s.strip()]
        legacy_roots = list(Category.objects.filter(slug__in=legacy_slugs))
        missing = set(legacy_slugs) - {c.slug for c in legacy_roots}
        if missing:
            raise CommandError(f"Не найдены legacy-корни: {', '.join(sorted(missing))}")

        # Узлы v2 к показу (всё поддерево, КРОМЕ «На модерацию»).
        mod = root.get_children().filter(name=_MODERATION_NAME).first()
        mod_ids = (
            {mod.id} | set(mod.get_descendants().values_list("id", flat=True)) if mod else set()
        )
        v2_nodes = [n for n in [root] + list(root.get_descendants()) if n.id not in mod_ids]

        self._report(doc, root, v2_nodes, mod, legacy_roots)

        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: видимость не изменена. Применить — --commit.")
            )
            return

        homeless = self._legacy_remaining(legacy_roots)
        if homeless and not options["force"]:
            raise CommandError(
                f"В скрываемых legacy останется видимых-в-дереве товаров: {homeless}. "
                "Проверьте отчётом catalog_v2_report; для продолжения добавьте --force."
            )
        self._commit(section, doc, root, v2_nodes, legacy_roots)

    # ------------------------------------------------------------------ #
    def _legacy_remaining(self, legacy_roots) -> int:
        ids = set()
        for r in legacy_roots:
            ids |= {r.id} | set(r.get_descendants().values_list("id", flat=True))
        return Product.objects.filter(category_id__in=ids).count()

    def _report(self, doc, root, v2_nodes, mod, legacy_roots):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"\n=== SWAP «{doc['section']}» (dry-run) ==="))
        w(f"v2-корень: {root.slug} (id={root.pk}) → показать узлов: {len(v2_nodes)}")
        w(f"  «{_MODERATION_NAME}» остаётся скрытым: {'есть' if mod else 'нет'}")
        if legacy_roots:
            w("Скрыть legacy-корни:")
            for r in legacy_roots:
                ids = {r.id} | set(r.get_descendants().values_list("id", flat=True))
                n = Product.objects.filter(category_id__in=ids).count()
                w(f"  - {r.slug} (id={r.pk}) — товаров в поддереве станут не видны в дереве: {n}")
        else:
            w(
                self.style.WARNING(
                    "Legacy-корни не заданы (--hide-legacy) — будет показан v2 без скрытия старого."
                )
            )

    def _commit(self, section, doc, root, v2_nodes, legacy_roots):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"swap-{section}-{ts}.json"
        redirect_path = backup_dir / f"redirects-{section}-{ts}.csv"
        backup = {"section": section, "nodes": []}

        with transaction.atomic():
            affected = (
                list(v2_nodes)
                + list(legacy_roots)
                + [d for r in legacy_roots for d in r.get_descendants()]
            )
            for n in affected:
                backup["nodes"].append({"id": n.id, "is_active": n.is_active, "on_site": n.on_site})

            # v2 → видимы
            v2_ids = [n.id for n in v2_nodes]
            Category.objects.filter(id__in=v2_ids).update(is_active=True, on_site=True)
            # legacy → скрыты (весь поддерев)
            for r in legacy_roots:
                ids = [r.id] + list(r.get_descendants().values_list("id", flat=True))
                Category.objects.filter(id__in=ids).update(is_active=False, on_site=False)

            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))
            self._write_redirects(redirect_path, root, legacy_roots)
            # bulk .update() обошёл post_save → сбрасываем кэш фасетов/дерева вручную,
            # иначе после свапа витрина отдаёт старую видимость/фасеты до TTL.
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSWAP применён: показано v2-узлов {len(v2_ids)}, скрыто legacy-корней "
                f"{len(legacy_roots)}. Откат: {backup_path}; план 301: {redirect_path}"
            )
        )
        self.stdout.write(
            "ВНИМАНИЕ: реальные 301/canonical не выставлены (модели redirect нет — Фаза 3). "
            "CSV — план для внедрения после появления механизма редиректов."
        )

    @staticmethod
    def _write_redirects(path: Path, v2_root: Category, legacy_roots) -> None:
        rows = []
        for r in legacy_roots:
            for cat in [r] + list(r.get_descendants()):
                rows.append(
                    {
                        "legacy_slug": cat.slug,
                        "legacy_path": " / ".join(
                            c.name for c in (list(cat.get_ancestors()) + [cat])
                        ),
                        "suggested_v2_slug": v2_root.slug,
                    }
                )
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["legacy_slug", "legacy_path", "suggested_v2_slug"]
            )
            writer.writeheader()
            writer.writerows(rows)

    # ------------------------------------------------------------------ #
    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Снимок не найден: {file_path}")
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise CommandError(f"Битый JSON: {exc}") from exc
        with transaction.atomic():
            for n in data.get("nodes", []):
                Category.objects.filter(id=n["id"]).update(
                    is_active=n["is_active"], on_site=n["on_site"]
                )
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK SWAP: восстановлена видимость {len(data.get('nodes', []))} узлов."
            )
        )
