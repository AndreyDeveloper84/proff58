"""E3 — построить раздел v2: создать узлы дерева + расселить товары по классификации.

По словарю ``data/product_type_rules.json`` (классификатор по смыслу названия,
НЕ по группам 1С):
1. создаёт узлы 2-го (и 3-го) уровня раздела (имена из правил, slug — латиница);
2. расселяет товары high-confidence в нужный узел, ставит ``category_is_manual=True``
   (защита от 1С); medium/low — НЕ трогает (очередь модерации);
3. ручную категорию (``category_is_manual=True``) НЕ перетирает.

    ./manage.py catalog_build_section --section osnastka            # dry-run
    ./manage.py catalog_build_section --section osnastka --commit    # применить
    ./manage.py catalog_build_section --rollback var/restructure/<файл>.json

``--commit`` — в транзакции, со снимком отката. Идемпотентно (уже размеченные —
manual=True — на повторном прогоне пропускаются).
"""

from __future__ import annotations

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


class Command(BaseCommand):
    help = "Построить раздел v2: создать узлы + расселить товары по классификации."

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTIONS))
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")
        parser.add_argument(
            "--min-confidence",
            choices=["high", "medium"],
            default="high",
            help="Минимальный confidence для авто-расселения (по умолчанию high).",
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

        # Классификация товаров БД (по названию). Цель — узел (subcat[/subtype]).
        min_rank = _CONF_RANK[options["min_confidence"]]
        assign: dict[tuple[str, str | None], list[int]] = {}
        skipped_manual = 0
        for p in Product.objects.values("id", "name", "category_is_manual"):
            hit = classify(p["name"], compiled)
            if hit is None:
                continue
            subcat, subtype, conf, _kw = hit
            if _CONF_RANK[conf] < min_rank:
                continue
            if p["category_is_manual"]:
                skipped_manual += 1
                continue
            key = (subcat, subtype if subtype in subtypes.get(subcat, []) else None)
            assign.setdefault(key, []).append(p["id"])

        self._report(cfg, subcats, subtypes, assign, skipped_manual, options["min_confidence"])
        if options["commit"]:
            self._commit(section, cfg, subcats, subtypes, assign)
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: ничего не создано и не перемещено. Применить — --commit."
                )
            )

    # ------------------------------------------------------------------ #
    def _report(self, cfg, subcats, subtypes, assign, skipped_manual, minconf):
        w = self.stdout.write
        root = (
            Category.objects.filter(slug=cfg["root_slug"]).first()
            or Category.objects.filter(name=cfg["root_name"]).first()
        )
        w(
            self.style.MIGRATE_HEADING(
                f"\n=== Построение раздела «{cfg['root_name']}» (dry-run) ==="
            )
        )
        w(
            f"Корень: {'есть, id=' + str(root.pk) if root else 'будет создан'}  slug={cfg['root_slug']}"
        )
        new_nodes = 0 if root else 1
        total_assign = 0
        w(self.style.MIGRATE_HEADING("\n-- Узлы и расселение (товаров к привязке) --"))
        for sc in subcats:
            n = len(assign.get((sc, None), []))
            sub_total = n + sum(len(assign.get((sc, st), [])) for st in subtypes.get(sc, []))
            total_assign += sub_total
            exists = root and root.get_children().filter(name=sc).exists() if root else False
            new_nodes += 0 if exists else 1
            w(f"  {sc:36s} {sub_total:5d}{'' if exists else '   (узел новый)'}")
            for st in subtypes.get(sc, []):
                cnt = len(assign.get((sc, st), []))
                if cnt:
                    new_nodes += 1
                    w(f"      → {st:30s} {cnt:5d}   (узел новый)")
        w(
            self.style.SUCCESS(
                f"\nИТОГО: создать узлов ~{new_nodes}; привязать товаров {total_assign} "
                f"(confidence ≥ {minconf}); пропущено ручных (category_is_manual) {skipped_manual}."
            )
        )

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
        node = parent.add_child(name=name, slug=self._unique_slug(name, parent), sort_order=order)
        created.append(node.pk)
        return node

    def _commit(self, section, cfg, subcats, subtypes, assign):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"build-{section}-{ts}.json"
        backup = {"section": section, "products": [], "created_nodes": []}
        moved: list[int] = []

        with transaction.atomic():
            root = (
                Category.objects.filter(slug=cfg["root_slug"]).first()
                or Category.objects.filter(name=cfg["root_name"]).first()
            )
            if root is None:
                root = Category.add_root(name=cfg["root_name"], slug=cfg["root_slug"])
                backup["created_nodes"].append(root.pk)

            node_map: dict[tuple[str, str | None], Category] = {}
            for i, sc in enumerate(subcats):
                sc_node = self._ensure_child(root, sc, i, backup["created_nodes"])
                node_map[(sc, None)] = sc_node
                for j, st in enumerate(subtypes.get(sc, [])):
                    node_map[(sc, st)] = self._ensure_child(sc_node, st, j, backup["created_nodes"])

            for key, ids in assign.items():
                target = node_map.get(key) or node_map.get((key[0], None))
                if target is None:
                    continue
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
                Product.objects.filter(id__in=ids).update(category=target, category_is_manual=True)
                moved += ids

            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))

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
                f"\nCOMMIT: создано узлов {len(backup['created_nodes'])}, привязано товаров "
                f"{len(moved)}. Снимок отката: {backup_path}"
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
