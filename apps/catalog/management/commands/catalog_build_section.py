"""E3 — построить раздел v2 СКРЫТЫМ: создать узлы + расселить товары по смыслу.

Вариант A («скрыто → секционный swap»). По словарю ``data/product_type_rules*.json``
(классификатор по названию, НЕ по группам 1С):

1. создаёт узлы 2-го (и 3-го) уровня раздела **скрытыми** (``is_active=False`` +
   ``on_site=False``) — витрина их не видит до финального swap (см.
   ``catalog_v2_swap``);
2. заводит на раздел скрытый узел **«На модерацию»** для «хвоста»;
3. high-confidence → нормальный узел, ``category_is_manual=True`` (защита от 1С);
4. medium/low (раздел матчит, но неуверенно) → узел «На модерацию», БЕЗ
   ``category_is_manual`` (ждут ручного разбора);
5. ручную категорию (``category_is_manual=True``) НЕ перетирает (только учитывает);
6. конфликт-чек (slug v2↔существующие, дубли имён) — печатает и (``--strict``) стопает;
7. пишет снимок отката и CSV модерации (операционный учёт «хвоста»).

    ./manage.py catalog_build_section --section krepezh             # dry-run
    ./manage.py catalog_build_section --section krepezh --commit     # применить (скрыто)
    ./manage.py catalog_build_section --rollback var/restructure/<файл>.json

``--commit`` — в транзакции, со снимком отката. Идемпотентно (уже размеченные —
manual=True — на повторном прогоне пропускаются; существующие узлы переиспользуются,
их видимость НЕ меняется — за видимость отвечает только swap).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.catalog.semantic import SECTION_RULES, classify, load_rules, translit_slug
from apps.core.events import EventSource, product_updated

# Раздел → файл словаря (общая карта в semantic.py). Имя/slug корня берутся
# из самого словаря (section / section_slug).
SECTIONS = SECTION_RULES
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}

# Имя скрытого узла-«хвоста» на раздел.
_MODERATION_NAME = "На модерацию"


class Command(BaseCommand):
    help = (
        "Построить раздел v2 (скрыто): узлы + расселение high → норма, medium/low → «На модерацию»."
    )

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTIONS))
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Останавливать --commit при найденных slug-конфликтах.",
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        section = options["section"]
        if not section:
            raise CommandError("Укажите --section или --rollback FILE.")
        try:
            doc, compiled = load_rules(SECTIONS[section])
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(f"Не прочитать правила: {exc}") from exc
        cfg = {
            "rules": SECTIONS[section],
            "root_name": doc["section"],
            "root_slug": doc["section_slug"],
        }

        # План узлов из правил (порядок первого появления).
        subcats: list[str] = []
        subtypes: dict[str, list[str]] = {}
        seen: set[str] = set()
        for subcat, subtype, *_ in compiled:
            if subcat not in seen:
                seen.add(subcat)
                subcats.append(subcat)
                subtypes[subcat] = []
            if subtype and subtype not in subtypes[subcat]:
                subtypes[subcat].append(subtype)

        # Классификация товаров БД (по названию). Три ведра:
        #   normal_assign  — high-confidence, не-manual → нормальный узел (manual=True);
        #   moderation_ids — medium/low, не-manual → узел «На модерацию» (manual не ставим);
        #   moderation_rows — строки CSV (операционный учёт хвоста);
        #   skipped_manual — уже размеченные вручную (manual=True) — не трогаем.
        normal_assign: dict[tuple[str, str | None], list[int]] = {}
        moderation_ids: list[int] = []
        moderation_rows: list[dict] = []
        skipped_manual = 0
        for p in Product.objects.values(
            "id",
            "name",
            "article",
            "category_id",
            "category__name",
            "category_is_manual",
            "available_quantity",
        ):
            hit = classify(p["name"], compiled)
            if hit is None:
                continue  # раздел не матчит — не его забота (глобальный хвост — в отчёте v2_report)
            subcat, subtype, conf, _kw = hit
            target_key = (subcat, subtype if subtype in subtypes.get(subcat, []) else None)
            if p["category_is_manual"]:
                # Уже размечен вручную/предыдущим разделом — не перетираем.
                skipped_manual += 1
                continue
            if _CONF_RANK[conf] >= _CONF_RANK["high"]:
                normal_assign.setdefault(target_key, []).append(p["id"])
            else:
                moderation_ids.append(p["id"])
                moderation_rows.append(
                    {
                        "section": section,
                        "product_id": p["id"],
                        "sku": p["article"] or "",
                        "name": p["name"],
                        "stock": p["available_quantity"],
                        "old_category": p["category__name"] or "",
                        "suggested_category": subcat + (f" / {subtype}" if target_key[1] else ""),
                        "confidence": conf,
                        "moderation_reason": "low_confidence",
                    }
                )

        conflicts = self._detect_slug_conflicts(cfg, subcats, subtypes)
        self._report(
            cfg, subcats, subtypes, normal_assign, moderation_ids, skipped_manual, conflicts
        )

        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: ничего не создано и не перемещено. Применить — --commit."
                )
            )
            return
        if conflicts and options["strict"]:
            raise CommandError(
                "Найдены slug-конфликты, а указан --strict. Разрешите конфликты или уберите --strict."
            )
        self._commit(
            section, cfg, subcats, subtypes, normal_assign, moderation_ids, moderation_rows
        )

    # ------------------------------------------------------------------ #
    def _detect_slug_conflicts(self, cfg, subcats, subtypes):
        """v2-slug, который уже занят СУЩЕСТВУЮЩЕЙ категорией вне этого раздела."""
        root_slug = cfg["root_slug"]
        root = Category.objects.filter(slug=root_slug).first()
        own = set()
        if root:
            own = {root.slug} | set(root.get_descendants().values_list("slug", flat=True))
        planned = {root_slug: cfg["root_name"]}
        for sc in subcats:
            planned[translit_slug(sc)] = sc
            for st in subtypes.get(sc, []):
                planned[translit_slug(st)] = st
        existing = dict(Category.objects.exclude(slug__in=own).values_list("slug", "name"))
        return [(slug, name, existing[slug]) for slug, name in planned.items() if slug in existing]

    # ------------------------------------------------------------------ #
    def _report(
        self, cfg, subcats, subtypes, normal_assign, moderation_ids, skipped_manual, conflicts
    ):
        w = self.stdout.write
        root = Category.objects.filter(slug=cfg["root_slug"]).first()
        w(
            self.style.MIGRATE_HEADING(
                f"\n=== Построение раздела «{cfg['root_name']}» (скрыто, dry-run) ==="
            )
        )
        w(
            f"Корень: {'есть, id=' + str(root.pk) if root else 'будет создан'}  slug={cfg['root_slug']}"
        )
        w("Видимость новых узлов: is_active=False, on_site=False (скрыто до swap).")
        new_nodes = 0 if root else 1
        total_normal = 0
        w(self.style.MIGRATE_HEADING("\n-- Узлы и расселение high-confidence --"))
        for sc in subcats:
            n = len(normal_assign.get((sc, None), []))
            sub_total = n + sum(len(normal_assign.get((sc, st), [])) for st in subtypes.get(sc, []))
            total_normal += sub_total
            exists = bool(root and root.get_children().filter(name=sc).exists())
            new_nodes += 0 if exists else 1
            w(f"  {sc:36s} {sub_total:5d}{'' if exists else '   (узел новый)'}")
            for st in subtypes.get(sc, []):
                cnt = len(normal_assign.get((sc, st), []))
                if cnt:
                    new_nodes += 1
                    w(f"      → {st:30s} {cnt:5d}   (узел новый)")
        w(
            self.style.SUCCESS(
                f"\nИТОГО: создать узлов ~{new_nodes + 1} (вкл. «{_MODERATION_NAME}»); "
                f"high → норма {total_normal}; medium/low → «{_MODERATION_NAME}» {len(moderation_ids)}; "
                f"пропущено ручных (manual) {skipped_manual}."
            )
        )
        if conflicts:
            w(
                self.style.ERROR(
                    f"\n⚠ SLUG-КОНФЛИКТЫ ({len(conflicts)}): v2-slug занят другой категорией:"
                )
            )
            for slug, planned_name, existing_name in conflicts[:20]:
                w(f"   slug='{slug}'  планируем «{planned_name}»  ↔ существует «{existing_name}»")
            w("   (на --commit slug будет авто-дополнен префиксом корня; с --strict — стоп.)")

    # ------------------------------------------------------------------ #
    def _unique_slug(self, name: str, parent: Category) -> str:
        base = translit_slug(name)
        slug = base
        if Category.objects.filter(slug=slug).exists():
            slug = f"{parent.slug}-{base}"
        return slug

    def _ensure_child(self, parent: Category, name: str, order: int, created: list[int]):
        node = parent.get_children().filter(name=name).first()
        if node:
            return node
        node = parent.add_child(
            name=name,
            slug=self._unique_slug(name, parent),
            sort_order=order,
            is_active=False,
            on_site=False,
        )
        created.append(node.pk)
        return node

    def _commit(
        self, section, cfg, subcats, subtypes, normal_assign, moderation_ids, moderation_rows
    ):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"build-{section}-{ts}.json"
        csv_path = backup_dir / f"moderation-{section}-{ts}.csv"
        backup = {"section": section, "products": [], "created_nodes": []}
        moved: list[int] = []

        with transaction.atomic():
            # Корень v2 — СТРОГО по slug (section_slug). Имя-фолбэк убран намеренно:
            # имя раздела в словаре часто совпадает с именем legacy-корня (свар­ка,
            # Крепёж…), и фолбэк по имени переиспользовал бы legacy как v2-корень,
            # ломая модель «скрытый build → swap». Нет узла по slug → создаём скрытым.
            root = Category.objects.filter(slug=cfg["root_slug"]).first()
            if root is None:
                root = Category.add_root(
                    name=cfg["root_name"],
                    slug=cfg["root_slug"],
                    is_active=False,
                    on_site=False,
                )
                backup["created_nodes"].append(root.pk)

            node_map: dict[tuple[str, str | None], Category] = {}
            for i, sc in enumerate(subcats):
                sc_node = self._ensure_child(root, sc, i, backup["created_nodes"])
                node_map[(sc, None)] = sc_node
                for j, st in enumerate(subtypes.get(sc, [])):
                    node_map[(sc, st)] = self._ensure_child(sc_node, st, j, backup["created_nodes"])

            moderation_node = self._ensure_child(
                root, _MODERATION_NAME, len(subcats), backup["created_nodes"]
            )

            # high → нормальный узел (manual=True)
            for key, ids in normal_assign.items():
                target = node_map.get(key) or node_map.get((key[0], None))
                if target is None:
                    continue
                self._snapshot(backup, ids)
                Product.objects.filter(id__in=ids).update(category=target, category_is_manual=True)
                moved += ids

            # medium/low → «На модерацию» (manual НЕ ставим — ждут разбора)
            if moderation_ids:
                self._snapshot(backup, moderation_ids)
                Product.objects.filter(id__in=moderation_ids).update(
                    category=moderation_node, category_is_manual=False
                )
                moved += moderation_ids

            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))
            self._write_moderation_csv(csv_path, moderation_rows)

            def _emit(pids=tuple(moved)):
                for pid in pids:
                    product_updated.send(
                        sender=Product,
                        product_id=pid,
                        source=EventSource.SYSTEM,
                        changed_fields=["category"],
                    )

            transaction.on_commit(_emit)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT (скрыто): создано узлов {len(backup['created_nodes'])}, "
                f"перемещено товаров {len(moved)} (в т.ч. в «{_MODERATION_NAME}» {len(moderation_ids)}). "
                f"Снимок отката: {backup_path}; CSV модерации: {csv_path}"
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

    @staticmethod
    def _write_moderation_csv(path: Path, rows: list[dict]) -> None:
        fields = [
            "section",
            "product_id",
            "sku",
            "name",
            "stock",
            "old_category",
            "suggested_category",
            "confidence",
            "moderation_reason",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
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
            for r in data.get("products", []):
                Product.objects.filter(id=r["id"]).update(
                    category_id=r["category_id"], category_is_manual=r["category_is_manual"]
                )
            # Удаляем созданные узлы (листья первыми — по глубине), только пустые.
            nodes = Category.objects.filter(id__in=data.get("created_nodes", []))
            for node in sorted(nodes, key=lambda c: c.depth, reverse=True):
                if not node.get_children().exists() and not node.products.exists():
                    node.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"ROLLBACK: восстановлено товаров {len(data.get('products', []))}, "
                f"удалено созданных узлов из {len(data.get('created_nodes', []))} (пустые)."
            )
        )
