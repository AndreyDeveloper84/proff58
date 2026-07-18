"""Создание CatalogProcessingRun + items для исследования/обогащения каталога.

Пример:

    python manage.py catalog_queue_create \\
        --only-untyped \\
        --in-stock \\
        --limit 20 \\
        --mode tool_type \\
        --kind research
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import (
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingMode,
    CatalogProcessingRun,
    CatalogProcessingRunKind,
    CatalogProcessingRunStatus,
    Product,
    ProductAttributeValue,
)
from apps.catalog.processing import canonical_hash, tool_type_snapshot

if TYPE_CHECKING:
    from collections.abc import Iterable


TOOL_TYPE_SLUG = "tool_type"
MAX_ITEMS = 1000


def _product_snapshot(product: Product) -> dict:
    """Канонический snapshot товара для export/audit."""
    category_path = ""
    if product.category_id:
        category_path = " / ".join(
            [category.name for category in product.category.get_ancestors()]
            + [product.category.name]
        )
    return {
        "product_id": product.pk,
        "code_1c": product.code_1c or "",
        "article": product.article or "",
        "barcode": product.barcode or "",
        "brand": product.brand or "",
        "name": product.name or "",
        "original_name": product.original_name or "",
        "category_id": product.category_id,
        "category_path": category_path,
        "source_group": product.source_group or "",
    }


def _products_without_tool_type():
    """QuerySet товаров без заполненного tool_type."""
    from django.db.models import Exists, OuterRef

    has_tool_type_with_option = ProductAttributeValue.objects.filter(
        product_id=OuterRef("pk"),
        attribute__slug=TOOL_TYPE_SLUG,
        value_option__isnull=False,
    )
    return Product.objects.annotate(has_tool_type=Exists(has_tool_type_with_option)).filter(
        has_tool_type=False
    )


class Command(BaseCommand):
    help = "Создать CatalogProcessingRun + items для исследования каталога."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=str,
            default=CatalogProcessingMode.TOOL_TYPE,
            choices=[CatalogProcessingMode.TOOL_TYPE],
            help="Режим обработки (v1 только tool_type).",
        )
        parser.add_argument(
            "--kind",
            type=str,
            default=CatalogProcessingRunKind.RESEARCH,
            choices=[
                CatalogProcessingRunKind.MANUAL,
                CatalogProcessingRunKind.RULES,
                CatalogProcessingRunKind.RESEARCH,
                CatalogProcessingRunKind.AI,
                CatalogProcessingRunKind.IMPORT,
            ],
            help="Тип запуска.",
        )
        parser.add_argument(
            "--only-untyped",
            action="store_true",
            help="Только товары без заполненного tool_type.",
        )
        parser.add_argument(
            "--in-stock",
            action="store_true",
            help="Только товары в наличии (available_quantity > 0).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Максимальное количество товаров в batch.",
        )
        parser.add_argument(
            "--idempotency-key",
            type=str,
            default=None,
            help="Ключ идемпотентности. По умолчанию генерируется из параметров.",
        )
        parser.add_argument(
            "--explicit-ids",
            type=str,
            default="",
            help="Список product id через запятую (переопределяет фильтры).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Не создавать run/item, только показать количество.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.FEATURES.get("catalog_processing", False):
            raise CommandError("Feature catalog_processing выключен.")

        mode = options["mode"]
        kind = options["kind"]
        only_untyped = options["only_untyped"]
        in_stock = options["in_stock"]
        limit = options["limit"]
        explicit_ids_str = options["explicit_ids"]
        dry_run = options["dry_run"]

        if not only_untyped and not explicit_ids_str:
            raise CommandError("Укажите --only-untyped или --explicit-ids.")
        if limit is not None and not (1 <= limit <= MAX_ITEMS):
            raise CommandError(f"--limit должен быть в диапазоне 1..{MAX_ITEMS}.")

        if explicit_ids_str:
            try:
                ids = sorted({int(x.strip()) for x in explicit_ids_str.split(",") if x.strip()})
            except ValueError as exc:
                raise CommandError(
                    "--explicit-ids должен содержать целые ID через запятую."
                ) from exc
            if not ids:
                raise CommandError("--explicit-ids не содержит ID.")
            if len(ids) > MAX_ITEMS:
                raise CommandError(f"Слишком много explicit IDs: {len(ids)} > {MAX_ITEMS}.")
            qs = Product.objects.filter(pk__in=ids)
        else:
            if limit is None:
                raise CommandError(f"Для безопасного запуска укажите --limit 1..{MAX_ITEMS}.")
            ids = []
            qs = Product.objects.all()
            if only_untyped:
                qs = qs.filter(pk__in=_products_without_tool_type().values("pk"))
            if in_stock:
                qs = qs.filter(available_quantity__gt=0)

        qs = qs.select_related("category").order_by("pk")
        if limit:
            qs = qs[:limit]

        products = list(qs)
        count = len(products)
        if explicit_ids_str:
            found_ids = {product.pk for product in products}
            missing_ids = sorted(set(ids) - found_ids)
            if missing_ids:
                raise CommandError(f"Не найдены product IDs: {missing_ids[:20]}")
        self.stdout.write(f"Найдено товаров: {count}")
        if dry_run:
            return

        scope = {
            "only_untyped": only_untyped,
            "in_stock": in_stock,
            "limit": limit,
            "explicit_ids": ids,
            "mode": mode,
            "kind": kind,
        }
        idempotency_key = options["idempotency_key"] or self._idempotency_key(options)
        existing = CatalogProcessingRun.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if existing.scope != scope:
                raise CommandError("Idempotency key уже используется run с другим scope.")
            self.stdout.write(
                self.style.WARNING(f"Run с таким idempotency key уже существует: {existing.pk}")
            )
            return str(existing.pk)

        try:
            with transaction.atomic():
                run = CatalogProcessingRun.objects.create(
                    kind=kind,
                    mode=mode,
                    status=CatalogProcessingRunStatus.RUNNING,
                    idempotency_key=idempotency_key,
                    scope=scope,
                    stats={"total_items": count},
                )
                items = self._build_items(run, products, mode)
                CatalogProcessingItem.objects.bulk_create(items, batch_size=500)
        except IntegrityError:
            existing = CatalogProcessingRun.objects.filter(idempotency_key=idempotency_key).first()
            if existing is None:
                raise
            if existing.scope != scope:
                raise CommandError("Idempotency key уже используется run с другим scope.") from None
            return str(existing.pk)

        self.stdout.write(self.style.SUCCESS(f"Создан run {run.pk} с {count} items"))
        return str(run.pk)

    @staticmethod
    def _idempotency_key(options: dict) -> str:
        payload = json.dumps(
            {
                "kind": options["kind"],
                "mode": options["mode"],
                "only_untyped": options["only_untyped"],
                "in_stock": options["in_stock"],
                "limit": options["limit"],
                "explicit_ids": sorted(
                    {
                        int(value.strip())
                        for value in options["explicit_ids"].split(",")
                        if value.strip()
                    }
                ),
                "date": timezone.now().strftime("%Y-%m-%d"),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_items(
        run: CatalogProcessingRun,
        products: Iterable[Product],
        mode: str,
    ) -> list[CatalogProcessingItem]:
        items: list[CatalogProcessingItem] = []
        for product in products:
            input_snapshot = _product_snapshot(product)
            baseline = tool_type_snapshot(product)
            baseline_hash = canonical_hash(
                {
                    "attribute_slug": baseline.get("attribute_slug"),
                    "option_slug": baseline.get("option_slug"),
                    "source": baseline.get("source"),
                    "confidence": baseline.get("confidence"),
                }
            )
            items.append(
                CatalogProcessingItem(
                    run=run,
                    product=product,
                    product_ref=product.pk,
                    status=CatalogProcessingItemStatus.PENDING,
                    input_snapshot=input_snapshot,
                    input_hash=canonical_hash(input_snapshot),
                    baseline_hashes={TOOL_TYPE_SLUG: baseline_hash},
                    needed_targets=[mode],
                )
            )
        return items
