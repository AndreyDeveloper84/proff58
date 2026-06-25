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

from apps.catalog.models import Category, Product, ProductAttributeValue, ProductStatus
from apps.catalog.services import products_in, tool_type_facets
from apps.core.events import EventSource, product_updated

POWER_SLUG = "power_source"
POWER_LABELS = {"Аккумулятор", "Сеть"}  # значения опций power_source — не типы инструмента
TOOL_TYPE_SLUG = "tool_type"
# tool_type-значения, которые на самом деле НЕ типы инструмента, а комплектующие
# (их место — подкатегория «Аккумуляторы и ЗУ», а не панель типов раздела).
COMPLEMENT_TOOL_TYPES = {"akkumulyatory", "zaryadnye"}

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


def _tool_type_buckets(qs) -> dict:
    """Разложить товары выборки по 3 корзинам по их tool_type.

    * ``tool`` — есть настоящий тип инструмента (не комплектующее) → переносить в раздел;
    * ``complement`` — tool_type ∈ комплектующие (Аккумуляторы/Зарядные) → в подкатегорию;
    * ``no_type`` — типа нет вовсе (кандидаты на «не-инструмент»: антенны/сварка/рации,
      разбираются отдельным шагом позже).
    """
    rows = ProductAttributeValue.objects.filter(
        product__in=qs,
        attribute__slug=TOOL_TYPE_SLUG,
        value_option__isnull=False,
    ).values_list("product_id", "value_option__slug")
    tool_ids: set[int] = set()
    compl_ids: set[int] = set()
    for pid, slug in rows:
        (compl_ids if slug in COMPLEMENT_TOOL_TYPES else tool_ids).add(pid)
    all_ids = set(qs.values_list("id", flat=True))
    # Назначение: инструмент И «без типа» → в раздел; только-комплектующие → подкатегория.
    section_ids = tool_ids | (all_ids - tool_ids - compl_ids)
    complement_ids = compl_ids - tool_ids
    return {
        "tool": len(tool_ids),
        "complement": len(complement_ids),
        "no_type": len(all_ids - tool_ids - compl_ids),
        "no_type_ids": sorted(all_ids - tool_ids - compl_ids),
        "section_ids": sorted(section_ids),
        "complement_ids": sorted(complement_ids),
    }


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
            self._commit(section, target, sources, keeps[0][1])
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

        # --- разбивка переносимых по tool_type-корзинам ---
        w(self.style.MIGRATE_HEADING("\n-- Разбивка переносимых по tool_type --"))
        b_tool = b_compl = b_none = 0
        none_ids: list[int] = []
        for _spec, cat in sources:
            b = _tool_type_buckets(products_in(cat))
            b_tool += b["tool"]
            b_compl += b["complement"]
            b_none += b["no_type"]
            none_ids += b["no_type_ids"]
            w(
                f"  «{cat.name}»: инструмент {b['tool']}  | комплектующие {b['complement']}  "
                f"| без типа {b['no_type']}"
            )
        w(
            self.style.SUCCESS(
                f"  ИТОГО: настоящий инструмент {b_tool}  | комплектующие (→ подкатегория) "
                f"{b_compl}  | без типа / не-инструмент {b_none}"
            )
        )
        if none_ids:
            w("  Примеры «без типа» (кандидаты на разбор отдельным шагом):")
            for name in (
                Product.objects.filter(id__in=none_ids[:12])
                .order_by("name")
                .values_list("name", flat=True)
            ):
                w(f"    – {name[:64]}")

        # --- узлы к скрытию ---
        w(self.style.MIGRATE_HEADING("\n-- Узлы к скрытию (is_active=False + on_site=False) --"))
        for _spec, cat in sources:
            w(f"  «{cat.name}» (slug={cat.slug}) — уйдёт из чипов-подкатегорий и резолва страницы")

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
        power_in = [t["value"] for t in types if t["value"] in POWER_LABELS]
        compl_in = [t["value"] for t in types if t["slug"] in COMPLEMENT_TOOL_TYPES]
        for t in types[:12]:
            mark = "  ← комплектующее" if t["slug"] in COMPLEMENT_TOOL_TYPES else ""
            w(f"  {t['value']:32s} {t['count']:5d}  ({t['slug']}){mark}")
        if power_in:
            w(self.style.ERROR(f"  ВНИМАНИЕ: в панели типов есть значения питания: {power_in}"))
        elif compl_in:
            w(
                self.style.WARNING(
                    f"  В панели типов есть комплектующие: {compl_in} — их место в подкатегории "
                    "«Аккумуляторы и ЗУ» (учтём в стратегии переноса)."
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
    def _commit(self, section, target, sources, complement_cat):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{section}-{ts}.json"
        backup = {"section": section, "target_id": target.pk, "products": [], "nodes": []}

        to_section: list[int] = []
        to_complement: list[int] = []
        with transaction.atomic():
            for _spec, cat in sources:
                qs = products_in(cat)
                # Снимок отката — по ВСЕМ товарам узла (вернём category/manual как было).
                for r in qs.values("id", "category_id", "category_is_manual"):
                    backup["products"].append(
                        {
                            "id": r["id"],
                            "category_id": r["category_id"],
                            "category_is_manual": r["category_is_manual"],
                        }
                    )
                b = _tool_type_buckets(qs)
                # Инструмент + «без типа» → раздел; только-комплектующие → подкатегорию.
                Product.objects.filter(id__in=b["section_ids"]).update(
                    category=target, category_is_manual=True
                )
                Product.objects.filter(id__in=b["complement_ids"]).update(
                    category=complement_cat, category_is_manual=True
                )
                to_section += b["section_ids"]
                to_complement += b["complement_ids"]
                # Скрываем опустевший узел И из витрины (is_active — по нему
                # фильтруются чипы-подкатегории и резолв страницы), И из публичного
                # дерева (on_site). Иначе остался бы пустой битый чип подкатегории.
                backup["nodes"].append(
                    {"id": cat.pk, "on_site": cat.on_site, "is_active": cat.is_active}
                )
                cat.on_site = False
                cat.is_active = False
                cat.save(update_fields=["on_site", "is_active"])

            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))

            def _emit(ids=tuple(to_section + to_complement)):
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
                f"\nCOMMIT: в раздел «{target.name}» {len(to_section)}, в подкатегорию "
                f"«{complement_cat.name}» {len(to_complement)}; скрыто узлов "
                f"{len(backup['nodes'])}. Снимок отката: {backup_path}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Не-инструмент «без типа» перенесён в раздел вместе с инструментом (как и был "
                "в поддереве) — типизацию и разбор хвоста делаем отдельным шагом. 301-redirect "
                "НЕ созданы (модели redirect нет — Фаза 3); обновите seed-маппинг "
                "data/group_mapping.json отдельным изменением (O6 плана)."
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
                fields = {"on_site": n["on_site"]}
                if "is_active" in n:  # снимки старого формата — без is_active
                    fields["is_active"] = n["is_active"]
                Category.objects.filter(id=n["id"]).update(**fields)

        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK: восстановлено товаров {len(data.get('products', []))}, "
                f"узлов {len(data.get('nodes', []))} из {path}."
            )
        )
