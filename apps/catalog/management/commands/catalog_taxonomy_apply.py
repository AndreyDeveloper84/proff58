"""Перестройка раздела каталога (Фаза 3) — безопасно, с dry-run и откатом.

Сейчас реализован раздел ``electroinstrument`` (см.
``docs/plans/electroinstrument-restructure.md``):

* схлопнуть «Сетевой инструмент» и «Аккумуляторный инструмент» в плоский
  «Электроинструмент» (питание остаётся фасетом ``power_source``);
* «Аккумуляторы и ЗУ» — отдельная подкатегория-комплектующие, не трогаем;
* опустевшие узлы скрываем (``on_site=False``), НЕ удаляем.

    ./manage.py catalog_taxonomy_apply --section electroinstrument            # dry-run
    ./manage.py catalog_taxonomy_apply --section electroinstrument --commit   # применить
    ./manage.py catalog_taxonomy_apply --rollback var/restructure/<файл>.json # откат

dry-run НИЧЕГО не меняет: печатает объёмы переноса, разбивку по видимости и
питанию, план 301-redirect, sample «до/после» и проверку TypePanel.
``--commit`` — в одной транзакции, со снимком отката. Идемпотентно.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductStatus
from apps.catalog.services import products_in, tool_type_facets
from apps.core.events import EventSource, product_updated

POWER_SLUG = "power_source"
POWER_LABELS = {"Аккумулятор", "Сеть"}  # значения опций power_source — не типы инструмента

# Описание разделов. Каждый «collapse» — узел, чьи товары переносятся в target,
# а сам узел скрывается; «keep» — остаётся как есть. ``power`` — ожидаемый
# вариант питания для текста redirect (после готовности canonical).
SECTIONS: dict[str, dict] = {
    "electroinstrument": {
        "target": {"slug": "elektroinstrument", "name": "Электроинструмент"},
        "collapse": [
            {"slug": "setevoy-instrument", "name": "Сетевой инструмент", "power": "mains"},
            {
                "slug": "akkumulyatornyy-instrument",
                "name": "Аккумуляторный инструмент",
                "power": "battery",
            },
        ],
        "keep": [
            {
                "slug": "akkumulyatory-i-zaryadnye-ustroystva",
                "name": "Аккумуляторы и зарядные устройства",
            },
        ],
    },
}


def _breadcrumb(cat: Category) -> str:
    return " / ".join([c.name for c in cat.get_ancestors()] + [cat.name])


def _power_filled(qs) -> int:
    """Сколько товаров выборки имеют заполненный select-атрибут питания."""
    return (
        qs.filter(
            attribute_values__attribute__slug=POWER_SLUG,
            attribute_values__value_option__isnull=False,
        )
        .distinct()
        .count()
    )


class Command(BaseCommand):
    help = "Перестройка раздела каталога: dry-run (по умолчанию) / --commit / --rollback."

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTIONS), help="Какой раздел.")
        parser.add_argument(
            "--commit", action="store_true", help="Применить изменения (иначе dry-run)."
        )
        parser.add_argument("--rollback", metavar="FILE", help="Откатить по снимку из файла.")
        parser.add_argument(
            "--samples", type=int, default=15, help="Сколько sample-товаров показать (dry-run)."
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        section = options["section"]
        if not section:
            raise CommandError("Укажите --section или --rollback FILE.")
        cfg = SECTIONS[section]

        target = self._resolve(cfg["target"])
        sources = [(spec, self._resolve(spec)) for spec in cfg["collapse"]]
        keeps = [(spec, self._resolve(spec)) for spec in cfg["keep"]]

        missing = [
            spec["slug"] for spec, cat in [(cfg["target"], target), *sources, *keeps] if cat is None
        ]
        if missing:
            raise CommandError(
                "Не найдены категории (по slug/name): " + ", ".join(missing) + ". "
                "Проверьте реальные slug на этой БД и поправьте SECTIONS."
            )

        self._report(section, target, sources, keeps, options["samples"])

        if options["commit"]:
            self._commit(section, target, sources)
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: изменения НЕ применены. Для применения добавьте --commit."
                )
            )

    # ------------------------------------------------------------------ #
    def _resolve(self, spec: dict) -> Category | None:
        return (
            Category.objects.filter(slug=spec["slug"]).first()
            or Category.objects.filter(name=spec["name"]).first()
        )

    def _report(self, section, target, sources, keeps, samples):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"\n=== Перестройка раздела «{section}» (dry-run отчёт) ==="))
        w(
            f"Целевой раздел: «{target.name}»  id={target.pk}  slug={target.slug}  "
            f"on_site={target.on_site}"
        )
        for _spec, cat in keeps:
            w(
                f"Остаётся подкатегорией: «{cat.name}»  slug={cat.slug}  "
                f"(товаров: {products_in(cat).count()})"
            )

        # --- объёмы переноса + разбивка ---
        w(self.style.MIGRATE_HEADING("\n-- Перенос товаров --"))
        total = visible = filled = 0
        per_source = []
        for spec, cat in sources:
            qs = products_in(cat)
            t = qs.count()
            v = qs.filter(is_active=True, status=ProductStatus.PUBLISHED).count()
            f = _power_filled(qs)
            per_source.append((spec, cat, t, v, f))
            total += t
            visible += v
            filled += f
            w(
                f"  «{cat.name}» (slug={cat.slug}): всего {t}  | on_site {v}  | "
                f"скрытых/неактивных {t - v}  | с питанием {f}  | без питания {t - f}"
            )
        w(
            self.style.SUCCESS(
                f"  ИТОГО к переносу: {total}  | on_site {visible}  | "
                f"скрытых/неактивных {total - visible}"
            )
        )
        w(
            f"  С заполненным питанием: {filled}  | "
            f"ОСТАНУТСЯ без питания после переноса: {total - filled}"
        )

        # --- redirects ---
        w(
            self.style.MIGRATE_HEADING(
                "\n-- 301-redirect (создание — Фаза 3: модели redirect ещё нет) --"
            )
        )
        for spec, cat in sources:
            w(
                f"  /catalog/{cat.slug}  →  /catalog/{target.slug}   "
                f"[врем. решение: без параметра]"
            )
            w(
                f"      после готовности canonical/noindex: "
                f"/catalog/{target.slug}?attr_power_source={spec['power']}"
            )
        w(
            self.style.WARNING(
                "  ВРЕМЕННОЕ РЕШЕНИЕ и SEO-риск: canonical/noindex для параметрических URL не\n"
                "  готовы → редиректим на раздел БЕЗ параметра (исключаем дубли). Сайт закрыт\n"
                "  (robots Disallow) — риск индексации сейчас нулевой. Параметрический таргет\n"
                "  включаем после внедрения canonical (см. план §4)."
            )
        )

        # --- TypePanel проверка ---
        w(self.style.MIGRATE_HEADING("\n-- TypePanel раздела (ось tool_type, не питание) --"))
        types = tool_type_facets(target)
        bad = [t for t in types if t["value"] in POWER_LABELS]
        for t in types[:12]:
            w(f"  {t['value']:32s} {t['count']:5d}  ({t['slug']})")
        if bad:
            w(
                self.style.ERROR(
                    f"  ВНИМАНИЕ: в панели типов есть значения питания: {[t['value'] for t in bad]}"
                )
            )
        else:
            w(
                self.style.SUCCESS(
                    "  OK: панель показывает типы инструмента; питание — отдельный фасет."
                )
            )

        # --- sample до/после ---
        w(self.style.MIGRATE_HEADING(f"\n-- Sample товаров «до → после» (до {samples}) --"))
        new_crumb = _breadcrumb(target)
        shown = 0
        for _spec, cat in sources:
            if shown >= samples:
                break
            for p in products_in(cat).order_by("id")[: samples - shown]:
                w(f"  • {p.name[:54]}")
                w(f"      slug={p.slug}")
                w(
                    f"      ДО:    категория «{cat.name}»  | {_breadcrumb(cat)}  | "
                    f"/catalog/{cat.slug}"
                )
                w(
                    f"      ПОСЛЕ: категория «{target.name}»  | {new_crumb}  | "
                    f"/catalog/{target.slug}"
                )
                shown += 1

    # ------------------------------------------------------------------ #
    def _commit(self, section, target, sources):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{section}-{ts}.json"
        backup = {"section": section, "target_id": target.pk, "products": [], "nodes": []}

        moved_ids: list[int] = []
        with transaction.atomic():
            for _spec, cat in sources:
                rows = list(products_in(cat).values("id", "category_id", "category_is_manual"))
                for r in rows:
                    backup["products"].append(
                        {
                            "id": r["id"],
                            "category_id": r["category_id"],
                            "category_is_manual": r["category_is_manual"],
                        }
                    )
                ids = [r["id"] for r in rows]
                Product.objects.filter(id__in=ids).update(category=target, category_is_manual=True)
                moved_ids += ids
                backup["nodes"].append({"id": cat.pk, "on_site": cat.on_site})
                cat.on_site = False
                cat.save(update_fields=["on_site"])

            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))

            def _emit(ids=tuple(moved_ids)):
                for pid in ids:
                    product_updated.send(
                        sender=Product,
                        product_id=pid,
                        source=EventSource.SYSTEM,
                        changed_fields=["category"],
                    )

            transaction.on_commit(_emit)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: перенесено {len(moved_ids)} товаров, скрыто узлов "
                f"{len(backup['nodes'])}. Снимок отката: {backup_path}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "301-redirect НЕ созданы (модели redirect нет — Фаза 3). Обновите также "
                "seed-маппинг data/group_mapping.json отдельным изменением (O6 плана)."
            )
        )

    # ------------------------------------------------------------------ #
    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Файл снимка не найден: {file_path}")
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise CommandError(f"Битый JSON снимка: {exc}") from exc

        with transaction.atomic():
            for r in data.get("products", []):
                Product.objects.filter(id=r["id"]).update(
                    category_id=r["category_id"],
                    category_is_manual=r["category_is_manual"],
                )
            for n in data.get("nodes", []):
                Category.objects.filter(id=n["id"]).update(on_site=n["on_site"])

        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK: восстановлено товаров {len(data.get('products', []))}, "
                f"узлов {len(data.get('nodes', []))} из {path}."
            )
        )
