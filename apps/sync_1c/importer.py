"""Сервис импорта номенклатуры из 1С с защитой ручной работы.

Главное правило интеграции:

    Из 1С обновляем:  цену, остаток, исходное название (original_name),
                      бренд (если на сайте пусто), активность в 1С.
    НЕ трогаем:       категорию сайта, витринное название (name), описание,
                      SEO, фото, slug, привязку к правилу — всё, что мог
                      изменить менеджер.

Так первичный «хаос» из 1С попадает на сайт один раз (как черновик), а
дальше каталог живёт самостоятельно и не ломается при каждой выгрузке.

Любой входящий элемент сперва пишется в NomenclatureStaging (сырой аудит),
затем создаётся/обновляется Product.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.catalog.categorization import ProductHint, categorize
from apps.catalog.models import Product, ProductStatus

from .models import NomenclatureStaging, StagingStatus


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    uncategorized: int = 0
    errors: int = 0

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


def _find_product(code_1c: str, article: str) -> Product | None:
    """Найти товар по коду 1С (приоритет), затем по артикулу."""
    if code_1c:
        product = Product.objects.filter(code_1c=code_1c).first()
        if product:
            return product
    if article:
        return Product.objects.filter(article=article).first()
    return None


def _create_product(item: dict) -> tuple[Product, bool]:
    """Создать товар из данных 1С. Вернуть (product, categorized?)."""
    name = item.get("name", "") or ""
    brand = item.get("brand", "") or ""
    article = item.get("sku") or item.get("article") or ""
    source_group = item.get("source_group", "") or ""

    category, rule = categorize(
        ProductHint(name=name, article=article, brand=brand, source_group=source_group)
    )

    product = Product(
        code_1c=item.get("external_id") or item.get("code_1c") or None,
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
        # авторазбор сработал → черновик; не сработал → требует проверки
        status=ProductStatus.DRAFT if category else ProductStatus.NEEDS_REVIEW,
    )
    _apply_price(product, item)
    _apply_stock(product, item)
    product.save()
    return product, category is not None


def _apply_price(product: Product, item: dict) -> None:
    price = _to_decimal(item.get("price"))
    if price is not None:
        product.price = price
        product.price_updated_at = timezone.now()
    old_price = _to_decimal(item.get("old_price"))
    if old_price is not None:
        product.old_price = old_price
    if item.get("currency"):
        product.currency = item["currency"]


def _apply_stock(product: Product, item: dict) -> None:
    stock = _to_decimal(item.get("stock"))
    reserved = _to_decimal(item.get("reserved"))
    available = _to_decimal(item.get("available_stock"))
    touched = False
    if stock is not None:
        product.stock_quantity = stock
        touched = True
    if reserved is not None:
        product.reserved_quantity = reserved
        touched = True
    if available is not None:
        product.available_quantity = available
        touched = True
    elif stock is not None:
        # доступно не прислали — считаем как остаток минус резерв
        product.available_quantity = stock - (reserved or product.reserved_quantity or 0)
        touched = True
    if touched:
        product.recalc_stock_status()
        product.stock_updated_at = timezone.now()


def _update_existing(product: Product, item: dict, *, allow_basic_fields: bool) -> None:
    """Обновить существующий товар, не затрагивая ручной контент сайта."""
    # Цена и остаток — всегда из 1С.
    _apply_price(product, item)
    _apply_stock(product, item)

    # Базовые поля-источники — только исходные, не витринные.
    if allow_basic_fields:
        if "name" in item and item["name"]:
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
def import_item(item: dict, *, allow_basic_fields: bool = True) -> tuple[Product, str]:
    """Импортировать один элемент. Вернуть (product, действие)."""
    code_1c = item.get("external_id") or item.get("code_1c") or ""
    article = item.get("sku") or item.get("article") or ""

    staging = NomenclatureStaging.objects.create(
        code_1c=code_1c,
        article=article,
        raw_payload=item,
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


def import_items(items: list[dict], *, allow_basic_fields: bool = True) -> ImportResult:
    """Импортировать пакет элементов из 1С."""
    result = ImportResult()
    for item in items:
        try:
            product, action = import_item(item, allow_basic_fields=allow_basic_fields)
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


def update_price(item: dict) -> bool:
    """Обновить только цену товара (POST /prices/update). Вернуть успех."""
    product = _find_product(
        item.get("external_id") or item.get("code_1c") or "",
        item.get("sku") or item.get("article") or "",
    )
    if product is None:
        return False
    _apply_price(product, item)
    product.save(update_fields=["price", "old_price", "currency", "price_updated_at"])
    return True


def update_stock(item: dict) -> bool:
    """Обновить только остаток товара (POST /stocks/update). Вернуть успех."""
    product = _find_product(
        item.get("external_id") or item.get("code_1c") or "",
        item.get("sku") or item.get("article") or "",
    )
    if product is None:
        return False
    _apply_stock(product, item)
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
