"""Структурный перенос товаров из курированного легаси-дерева в одноимённые v2-узлы.

Для разделов, где легаси УЖЕ вручную разложен (``category_is_manual=True``) и совпадает
с v2-скелетом по именам подкатегорий (напр. Крепёж): переносим товары каждой
легаси-подкатегории в v2-узел с ТЕМ ЖЕ именем, СОХРАНЯЯ ручную курацию. В отличие от
``catalog_build_section`` (словарная классификация по НАЗВАНИЮ ТОВАРА) здесь источник
истины структуры — сами легаси-категории (их раскладывал человек).

    ./manage.py catalog_remap_legacy --section krepezh --from krepezh-i-metizy          # dry-run
    ./manage.py catalog_remap_legacy --section krepezh --from krepezh-i-metizy --commit  # применить
    ./manage.py catalog_remap_legacy --rollback var/restructure/remap-<...>.json

Если таксономии расходятся по именам (легаси-подкатегория названа иначе, чем v2-узел),
явные пары задаются через ``--map 'Легаси-имя=v2-имя'`` (повторяемо):

    ./manage.py catalog_remap_legacy --section osnastka --from osnastka-i-rashodniki \\
        --map 'Отрезные и шлифовальные круги=Круги' \\
        --map 'Алмазные круги=Алмазная оснастка' --commit

Матчинг — по нормализованному имени (lower, ё→е, схлоп пробелов). Несопоставленные
легаси-узлы (нет v2-пары) НЕ трогаются — печатаются как хвост на разбор. v2-узлы
переиспользуются по имени (их создаёт ``catalog_build_skeleton``); НОВЫХ узлов команда
не создаёт. Перенесённым товарам ставится ``category_is_manual=True`` (защита от 1С,
курация переезжает вместе с товаром). Видимость v2/скрытие легаси — отдельно
(``catalog_v2_swap``). Идемпотентно, в транзакции, со снимком отката.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Category, Product
from apps.catalog.semantic import SECTION_RULES
from apps.core.events import EventSource, product_updated


def _norm(s: str) -> str:
    """Нормализация имени для матчинга: lower, ё→е, схлоп пробелов."""
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("ё", "е"))


class Command(BaseCommand):
    help = "Структурный перенос товаров из курированного легаси-дерева в одноимённые v2-узлы."

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTION_RULES))
        parser.add_argument("--from", dest="legacy", metavar="LEGACY_SLUG")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")
        parser.add_argument(
            "--map",
            dest="maps",
            action="append",
            default=[],
            metavar="LEGACY=V2",
            help="Явное соответствие имён, когда легаси-подкатегория названа иначе, чем "
            "v2-узел (повторяемо): --map 'Отрезные и шлифовальные круги=Круги'.",
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        section = options["section"]
        legacy_slug = options["legacy"]
        if not section or not legacy_slug:
            raise CommandError(
                "Укажите --section <slug> и --from <legacy-slug> (или --rollback FILE)."
            )

        v2 = Category.objects.filter(slug=section, is_site_v2=True).first()
        if v2 is None:
            raise CommandError(
                f"v2-корень раздела не найден: slug={section}, is_site_v2=True. "
                "Сначала catalog_build_skeleton."
            )
        legacy = Category.objects.filter(slug=legacy_slug).first()
        if legacy is None:
            raise CommandError(f"Легаси-корень не найден: slug={legacy_slug}.")
        if legacy.pk == v2.pk:
            raise CommandError("--from совпадает с v2-корнем раздела.")

        # Карта v2 по нормализованному имени (потомки корня; сам корень исключаем —
        # товары на корень раздела не кладём).
        v2_by_name: dict[str, Category] = {}
        for node in v2.get_descendants():
            v2_by_name.setdefault(_norm(node.name), node)

        # Явные соответствия имён (для расходящихся таксономий): легаси-имя → v2-имя.
        explicit: dict[str, str] = {}
        for m in options.get("maps") or []:
            if "=" not in m:
                raise CommandError(f"--map ожидает 'Легаси-имя=v2-имя', получено: {m!r}")
            leg_name, v2_name = m.split("=", 1)
            v2_key = _norm(v2_name)
            if v2_key not in v2_by_name:
                raise CommandError(
                    f"--map: v2-узел «{v2_name.strip()}» не найден среди подкатегорий раздела."
                )
            explicit[_norm(leg_name)] = v2_key

        # План: для каждого легаси-узла (корень + потомки) — его ПРЯМЫЕ товары → одноимённый
        # v2-узел (или указанный через --map). Узлы без v2-пары — в хвост (не трогаем).
        plan: list[tuple[Category, Category, list[int]]] = []
        unmatched: list[tuple[Category, int]] = []
        for ln in [legacy] + list(legacy.get_descendants()):
            pids = list(Product.objects.filter(category_id=ln.id).values_list("id", flat=True))
            if not pids:
                continue
            key = _norm(ln.name)
            target = v2_by_name.get(key) or v2_by_name.get(explicit.get(key, ""))
            if target is None or target.pk == ln.pk:
                unmatched.append((ln, len(pids)))
                continue
            plan.append((ln, target, pids))

        self._report(v2, legacy, plan, unmatched)
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не перенесено. Применить — --commit.")
            )
            return
        if not plan:
            self.stdout.write(
                self.style.WARNING("Нечего переносить (нет сопоставленных по имени узлов).")
            )
            return
        self._commit(section, legacy_slug, plan)

    # ------------------------------------------------------------------ #
    def _report(self, v2, legacy, plan, unmatched):
        w = self.stdout.write
        w(
            self.style.MIGRATE_HEADING(
                f"\n=== Перенос «{legacy.name}» → v2 «{v2.name}» (dry-run) ==="
            )
        )
        w(self.style.MIGRATE_HEADING("\n-- Сопоставлено по имени (легаси → v2) --"))
        total = 0
        for ln, target, pids in sorted(plan, key=lambda r: -len(r[2])):
            total += len(pids)
            w(f"  {ln.name:34s} {len(pids):5d} → v2 «{target.name}» (slug={target.slug})")
        w(self.style.SUCCESS(f"\nИТОГО к переносу: {total} товаров в {len(plan)} v2-узлов."))
        if unmatched:
            w(
                self.style.WARNING(
                    "\nНе сопоставлено (нет v2-пары — останутся в легаси, хвост на разбор):"
                )
            )
            for ln, n in sorted(unmatched, key=lambda r: -r[1]):
                w(f"  {ln.name:34s} {n:5d}")

    # ------------------------------------------------------------------ #
    def _commit(self, section, legacy_slug, plan):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"remap-{section}-{ts}.json"
        backup = {"section": section, "from": legacy_slug, "products": []}
        moved: list[int] = []

        with transaction.atomic():
            for _ln, target, pids in plan:
                self._snapshot(backup, pids)
                Product.objects.filter(id__in=pids).update(category=target, category_is_manual=True)
                moved += pids
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))

            def _emit(pids=tuple(moved)):
                for pid in pids:
                    product_updated.send(
                        sender=Product,
                        product_id=pid,
                        source=EventSource.SYSTEM,
                        changed_fields=["category"],
                    )
                # bulk .update() обошёл post_save → инвалидация кэшей вручную.
                invalidate_facets_cache()
                invalidate_category_tree_cache()

            transaction.on_commit(_emit)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: перенесено товаров {len(moved)} в {len(plan)} v2-узлов. "
                f"Снимок отката: {backup_path}"
            )
        )

    @staticmethod
    def _snapshot(backup: dict, ids: list[int]) -> None:
        for r in Product.objects.filter(id__in=ids).values(
            "id", "category_id", "category_is_manual"
        ):
            backup["products"].append(
                {
                    "id": r["id"],
                    "category_id": r["category_id"],
                    "category_is_manual": r["category_is_manual"],
                }
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
        with transaction.atomic():
            for r in data.get("products", []):
                Product.objects.filter(id=r["id"]).update(
                    category_id=r["category_id"], category_is_manual=r["category_is_manual"]
                )
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(f"ROLLBACK: восстановлено товаров {len(data.get('products', []))}.")
        )
