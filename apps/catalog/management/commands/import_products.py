"""Импорт товаров из ``catalog_fixed.json`` (тестовая выгрузка 1С).

Товар привязывается к категории по ``external_id`` его РОДИТЕЛЬСКОЙ группы 1С
(резолв через ``site_path`` маппинга — не по ``source_group``: имя не уникально).
Товары групп ``on_site:false`` импортируются, но помечаются категорией
«Не на сайте». Идемпотентно (upsert по ``code_1c``). Пишет ``ImportRun``.

Контентные поля (витринное имя) не перезаписываются при ``content_locked=True``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.ingest import (
    group_index,
    iter_products,
    load_group_mapping,
    load_json,
    stock_value,
)
from apps.catalog.management.commands.build_categories import OFFSITE_ROOT_NAME
from apps.catalog.models import (
    Category,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductStatus,
    StockStatus,
)

BATCH = 1000


class Command(BaseCommand):
    help = "Импортировать товары из data/catalog_fixed.json (идемпотентно, пишет ImportRun)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с входными файлами")

    def handle(self, *args, **options):
        mapping = load_group_mapping(options["path"])
        gindex = group_index(mapping)
        tree = load_json("catalog_fixed.json", options["path"])

        cat_by_external = self._resolve_categories(mapping)

        run = ImportRun.objects.create(source="catalog_fixed.json")
        stats = {
            "products_imported": 0,
            "excluded": 0,
            "in_stock_on_site": 0,
            "in_stock_excluded": 0,
            "unmatched_group": 0,
        }

        existing = {p.code_1c: p for p in Product.objects.exclude(code_1c__isnull=True)}
        to_create: list[Product] = []
        to_update: list[Product] = []

        try:
            # Весь импорт — в одной транзакции: сбой на середине не должен
            # оставлять полу-импортированный каталог (#4). ImportRun(FAILED)
            # пишем В except ВНЕ этого блока — иначе аудит откатится вместе с данными.
            with transaction.atomic():
                for node, parent_gid in iter_products(tree):
                    ext = str(node.get("external_id")) if node.get("external_id") else None
                    if not ext:
                        continue
                    row = gindex.get(str(parent_gid)) if parent_gid else None
                    category = cat_by_external.get(str(parent_gid)) if parent_gid else None
                    on_site = bool(row and row.get("on_site"))
                    stock = stock_value(node)

                    if row is None:
                        stats["unmatched_group"] += 1
                    if on_site:
                        stats["products_imported"] += 1
                        if stock > 0:
                            stats["in_stock_on_site"] += 1
                    else:
                        stats["excluded"] += 1
                        if stock > 0:
                            stats["in_stock_excluded"] += 1

                    obj = existing.get(ext)
                    if obj is None:
                        to_create.append(self._build(node, ext, category, stock))
                        if len(to_create) >= BATCH:
                            Product.objects.bulk_create(to_create, batch_size=BATCH)
                            to_create.clear()
                    else:
                        if self._apply(obj, node, category, stock):
                            to_update.append(obj)
                        if len(to_update) >= BATCH:
                            self._flush_update(to_update)

                if to_create:
                    Product.objects.bulk_create(to_create, batch_size=BATCH)
                if to_update:
                    self._flush_update(to_update)

            run.status = ImportRunStatus.DONE
        except Exception as exc:  # noqa: BLE001 — лог и проброс
            run.status = ImportRunStatus.FAILED
            stats["error"] = str(exc)
            run.finished_at = timezone.now()
            run.stats = stats
            run.save()
            raise

        run.finished_at = timezone.now()
        run.stats = stats
        run.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт: на сайте {stats['products_imported']} "
                f"(в наличии {stats['in_stock_on_site']}), "
                f"исключено {stats['excluded']} (в наличии {stats['in_stock_excluded']}), "
                f"итого {stats['products_imported'] + stats['excluded']}."
            )
        )
        return str(run.pk)

    # --- резолв категорий по site_path -----------------------------------

    def _resolve_categories(self, mapping: list[dict]) -> dict[str, Category]:
        """external_id группы 1С → лист Category (по site_path, дубли — на один лист)."""
        offsite_root = Category.objects.filter(depth=1, name=OFFSITE_ROOT_NAME).first()
        result: dict[str, Category] = {}
        for row in mapping:
            ext = str(row["external_id"])
            if row.get("on_site") and row.get("site_path"):
                node = self._walk(row["site_path"])
            elif offsite_root is not None:
                node = (
                    offsite_root.get_children()
                    .filter(name=(row.get("group_1c") or ext).strip())
                    .first()
                )
            else:
                node = None
            if node is not None:
                result[ext] = node
        return result

    @staticmethod
    def _walk(names: list[str]) -> Category | None:
        parent: Category | None = None
        for name in names:
            qs = (
                Category.objects.filter(depth=1, name=name.strip())
                if parent is None
                else parent.get_children().filter(name=name.strip())
            )
            node = qs.first()
            if node is None:
                return None
            parent = node
        return parent

    # --- построение/обновление товара ------------------------------------

    @staticmethod
    def _stock_status(stock: float) -> str:
        return StockStatus.IN_STOCK if stock > 0 else StockStatus.OUT_OF_STOCK

    def _build(self, node: dict, ext: str, category: Category | None, stock: float) -> Product:
        name = (node.get("name") or "").strip()[:512]
        return Product(
            code_1c=ext,
            slug=ext,  # уникален по построению (external_id уникален в 1С)
            article=(node.get("sku") or "").strip()[:100],
            barcode=(node.get("barcode") or "").strip()[:64],
            original_name=name,
            name=name or ext,
            source_group=(node.get("source_group") or "").strip()[:255],
            unit=(node.get("unit") or "").strip()[:32],
            is_active_1c=str(node.get("is_active")) in ("1", "True", "true"),
            category=category,
            stock_quantity=stock,
            available_quantity=stock,
            stock_status=self._stock_status(stock),
            status=ProductStatus.IMPORTED,
            is_active=False,
        )

    def _apply(self, obj: Product, node: dict, category: Category | None, stock: float) -> bool:
        """Обновить поля из 1С. Контентные поля защищены content_locked. Возврат — менялось ли."""
        changed = False

        def setattr_if(field: str, value):
            nonlocal changed
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed = True

        name = (node.get("name") or "").strip()[:512]
        setattr_if("original_name", name)
        setattr_if("source_group", (node.get("source_group") or "").strip()[:255])
        setattr_if("unit", (node.get("unit") or "").strip()[:32])
        setattr_if("article", (node.get("sku") or "").strip()[:100])
        setattr_if("is_active_1c", str(node.get("is_active")) in ("1", "True", "true"))
        setattr_if("stock_quantity", stock)
        setattr_if("available_quantity", stock)
        setattr_if("stock_status", self._stock_status(stock))

        # Категория: авторазбор не трогает назначенную вручную.
        if not obj.category_is_manual and obj.category_id != (category.id if category else None):
            obj.category = category
            changed = True

        # Витринное имя — контентное поле; не перезаписываем при блокировке.
        if not obj.content_locked and not obj.name:
            obj.name = name or obj.code_1c
            changed = True

        return changed

    @staticmethod
    def _flush_update(batch: list[Product]) -> None:
        Product.objects.bulk_update(
            batch,
            fields=[
                "original_name",
                "source_group",
                "unit",
                "article",
                "is_active_1c",
                "stock_quantity",
                "available_quantity",
                "stock_status",
                "category",
                "name",
            ],
            batch_size=BATCH,
        )
        batch.clear()
