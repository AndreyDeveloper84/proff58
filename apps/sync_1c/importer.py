"""Сервис импорта номенклатуры из 1С с защитой ручной работы.

Главное правило интеграции:

    Из 1С обновляем:  цену, остаток, исходное название (original_name),
                      бренд (если на сайте пусто), активность в 1С.
    НЕ трогаем:       категорию сайта, витринное название (name), описание,
                      SEO, фото, slug, привязку к правилу — всё, что мог
                      изменить менеджер.

Так первичный «хаос» из 1С попадает на сайт один раз (как черновик), а
дальше каталог живёт самостоятельно и не ломается при каждой выгрузке.

Идемпотентность:
  * товар ищется по коду 1С (unique), затем по артикулу — повторный импорт
    обновляет существующий товар, а не плодит дубли;
  * цена/остаток ведутся как «текущая запись + история» (PriceRecord /
    StockRecord) с инвариантом «одна актуальная цена на код+тип+валюту»;
  * каждая строка пишется в NomenclatureStaging с row_hash и ссылкой на
    прогон (SyncLog) — для трассировки и выявления повторов.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.catalog.categorization import ProductHint, categorize
from apps.catalog.models import Product, ProductStatus

from .models import NomenclatureStaging, PriceRecord, StagingStatus, StockRecord, SyncLog


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    uncategorized: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.errors

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "uncategorized": self.uncategorized,
            "errors": self.errors,
        }


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _row_hash(item: dict) -> str:
    payload = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _code_of(item: dict) -> str:
    return item.get("external_id") or item.get("code_1c") or ""


def _article_of(item: dict) -> str:
    return item.get("sku") or item.get("article") or ""


def _find_product(code_1c: str, article: str) -> Product | None:
    """Найти товар по коду 1С (приоритет), затем по артикулу."""
    if code_1c:
        product = Product.objects.filter(code_1c=code_1c).first()
        if product:
            return product
    if article:
        return Product.objects.filter(article=article).first()
    return None


# --- Запись цены и остатка (Product-денормализация + история в записях 1С) ---


def set_current_price(product: Product, item: dict) -> bool:
    """Обновить цену товара и завести актуальную запись PriceRecord."""
    price = _to_decimal(item.get("price"))
    if price is None:
        return False
    old_price = _to_decimal(item.get("old_price"))
    currency = item.get("currency") or product.currency or "RUB"
    price_type = item.get("price_type") or "retail"

    product.price = price
    if old_price is not None:
        product.old_price = old_price
    product.currency = currency
    product.price_updated_at = timezone.now()

    if product.code_1c:
        # Снимаем флаг актуальности со старой цены, затем пишем новую.
        PriceRecord.objects.filter(
            code_1c=product.code_1c, price_type=price_type, currency=currency, is_current=True
        ).update(is_current=False)
        PriceRecord.objects.create(
            code_1c=product.code_1c,
            product=product,
            price_type=price_type,
            value=price,
            currency=currency,
            is_current=True,
        )
    return True


def set_current_stock(product: Product, item: dict) -> bool:
    """Обновить остаток товара и запись StockRecord по складу."""
    stock = _to_decimal(item.get("stock"))
    reserved = _to_decimal(item.get("reserved"))
    available = _to_decimal(item.get("available_stock"))
    warehouse = item.get("warehouse") or "main"

    if stock is None and reserved is None and available is None:
        return False

    if stock is not None:
        product.stock_quantity = stock
    if reserved is not None:
        product.reserved_quantity = reserved
    if available is not None:
        product.available_quantity = available
    elif stock is not None:
        product.available_quantity = stock - (reserved or product.reserved_quantity or 0)

    product.recalc_stock_status()
    product.stock_updated_at = timezone.now()

    if product.code_1c and stock is not None:
        StockRecord.objects.update_or_create(
            code_1c=product.code_1c,
            warehouse=warehouse,
            defaults={"product": product, "quantity": stock},
        )
    return True


# --- Создание и обновление товара ---


def _create_product(item: dict) -> tuple[Product, bool]:
    name = item.get("name", "") or ""
    brand = item.get("brand", "") or ""
    article = _article_of(item)
    source_group = item.get("source_group", "") or ""

    category, rule = categorize(
        ProductHint(name=name, article=article, brand=brand, source_group=source_group)
    )

    product = Product(
        code_1c=_code_of(item) or None,
        article=article,
        barcode=item.get("barcode", "") or "",
        original_name=name,
        name=name,  # витринное имя при создании = имя из 1С; далее правится вручную
        brand=brand,
        source_group=source_group,
        unit=item.get("unit", "") or "",
        is_active_1c=item.get("is_active"),
        category=category,
        matched_rule=rule,
        status=ProductStatus.DRAFT if category else ProductStatus.NEEDS_REVIEW,
    )
    product.save()  # нужен pk для записей цены/остатка
    set_current_price(product, item)
    set_current_stock(product, item)
    product.save()
    return product, category is not None


def _update_existing(product: Product, item: dict, *, allow_basic_fields: bool) -> None:
    """Обновить существующий товар, не затрагивая ручной контент сайта."""
    set_current_price(product, item)
    set_current_stock(product, item)

    if allow_basic_fields:
        if item.get("name"):
            product.original_name = item["name"]  # витринное name НЕ трогаем
        if item.get("brand") and not product.brand:
            product.brand = item["brand"]
        if item.get("barcode"):
            product.barcode = item["barcode"]
        if item.get("unit"):
            product.unit = item["unit"]
        if "is_active" in item:
            product.is_active_1c = item["is_active"]
        if item.get("source_group"):
            product.source_group = item["source_group"]

    # Категория, name(витрина), description, SEO, фото, slug — НЕ трогаем.
    product.save()


@transaction.atomic
def import_item(
    item: dict,
    *,
    allow_basic_fields: bool = True,
    sync_log: SyncLog | None = None,
    source_file: str = "",
) -> tuple[Product, str]:
    """Импортировать один элемент. Вернуть (product, действие)."""
    code_1c = _code_of(item)
    article = _article_of(item)

    staging = NomenclatureStaging.objects.create(
        code_1c=code_1c,
        article=article,
        raw_payload=item,
        row_hash=_row_hash(item),
        sync_log=sync_log,
        source_file=source_file or (sync_log.source_file if sync_log else ""),
        name_1c=item.get("name", "") or "",
        unit=item.get("unit", "") or "",
        price=_to_decimal(item.get("price")),
        stock=_to_decimal(item.get("stock")),
        is_active_1c=item.get("is_active"),
    )

    product = _find_product(code_1c, article)
    if product is None:
        product, categorized = _create_product(item)
        action = "created"
        staging.status = StagingStatus.MATCHED if categorized else StagingStatus.NEW
    else:
        _update_existing(product, item, allow_basic_fields=allow_basic_fields)
        action = "updated"
        staging.status = StagingStatus.MATCHED

    staging.product = product
    staging.processed_at = timezone.now()
    staging.save(update_fields=["product", "status", "processed_at"])
    return product, action


def import_items(items: list[dict], *, allow_basic_fields: bool = True, **kwargs) -> ImportResult:
    """Импортировать пакет элементов из 1С."""
    result = ImportResult()
    for item in items:
        try:
            product, action = import_item(item, allow_basic_fields=allow_basic_fields, **kwargs)
        except Exception:  # noqa: BLE001 — ошибка одного товара не валит весь пакет
            result.errors += 1
            continue
        if action == "created":
            result.created += 1
            if product.category_id is None:
                result.uncategorized += 1
        else:
            result.updated += 1
    return result


def run_import(
    items: list[dict],
    *,
    sync_type: str = SyncLog.SyncType.FULL,
    source_file: str = "",
    allow_basic_fields: bool = True,
) -> tuple[SyncLog, ImportResult]:
    """Выполнить прогон импорта: создать SyncLog, импортировать, связать строки."""
    sync_log = SyncLog.objects.create(
        sync_type=sync_type, source_file=source_file, result=SyncLog.SyncResult.OK
    )
    result = import_items(
        items, allow_basic_fields=allow_basic_fields, sync_log=sync_log, source_file=source_file
    )
    sync_log.rows_total = len(items)
    sync_log.rows_ok = result.created + result.updated
    sync_log.rows_error = result.errors
    sync_log.result = SyncLog.SyncResult.OK if result.errors == 0 else SyncLog.SyncResult.PARTIAL
    sync_log.finished_at = timezone.now()
    sync_log.save()
    return sync_log, result


# --- Точечные обновления только цены / только остатка ---


def update_price(item: dict) -> bool:
    """Обновить только цену товара (POST /prices/update)."""
    product = _find_product(_code_of(item), _article_of(item))
    if product is None:
        return False
    if not set_current_price(product, item):
        return False
    product.save(update_fields=["price", "old_price", "currency", "price_updated_at"])
    return True


def update_stock(item: dict) -> bool:
    """Обновить только остаток товара (POST /stocks/update)."""
    product = _find_product(_code_of(item), _article_of(item))
    if product is None:
        return False
    if not set_current_stock(product, item):
        return False
    product.save(
        update_fields=[
            "stock_quantity",
            "reserved_quantity",
            "available_quantity",
            "stock_status",
            "stock_updated_at",
        ]
    )
    return True
