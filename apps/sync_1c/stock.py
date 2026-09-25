"""Остатки: денормализация в Product + запись StockRecord по складу."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from apps.catalog.models import Product

from . import matching
from .models import StockRecord
from .normalizers import Item

_STOCK_FIELDS = [
    "stock_quantity",
    "reserved_quantity",
    "available_quantity",
    "stock_status",
    "stock_updated_at",
]

_ZERO = Decimal("0")


def _available_from(product: Product, item: Item) -> Decimal | None:
    """Свободный остаток по данным 1С, зажатый в ноль. None — данных нет.

    1С может прислать резерв больше остатка (или прямо отрицательный `available`).
    Минус в `available_quantity` запрещён constraint'ом (DRF-1003), а ронять из-за
    одной такой строки весь пакетный обмен нельзя — поэтому зажимаем, а не падаем.
    """
    if item.available_stock is not None:
        value = item.available_stock
    elif item.stock is not None:
        value = item.stock - (item.reserved or product.reserved_quantity or _ZERO)
    else:
        return None
    return max(_ZERO, value)


def set_current_stock(product: Product, item: Item) -> bool:
    """Записать остаток в Product и StockRecord по складу. Не сохраняет Product."""
    if item.stock is None and item.reserved is None and item.available_stock is None:
        return False

    warehouse = item.warehouse or "main"

    if item.stock is not None:
        product.stock_quantity = item.stock
    if item.reserved is not None:
        product.reserved_quantity = item.reserved
    available = _available_from(product, item)
    if available is not None:
        product.available_quantity = available

    product.recalc_stock_status()
    product.stock_updated_at = timezone.now()

    if product.code_1c and item.stock is not None:
        StockRecord.objects.update_or_create(
            code_1c=product.code_1c,
            warehouse=warehouse,
            defaults={"product": product, "quantity": item.stock},
        )
    return True


def update_stock(item: Item) -> bool:
    """Точечно применить остаток к найденному товару (find-first). Используется shim'ом."""
    product = matching.find_product(item)
    if product is None:
        return False
    if not set_current_stock(product, item):
        return False
    product.save(update_fields=_STOCK_FIELDS)
    return True


# --- Пакетные остатки (#125B) ---


@dataclass
class StockPlan:
    """Запланированная запись остатка по складу (Product уже промутирован)."""

    product: Product
    code_1c: str
    warehouse: str
    quantity: Decimal


def plan_stock(product: Product, item: Item) -> StockPlan | None:
    """Промутировать денормализацию остатка в Product (БЕЗ записи StockRecord).

    Зеркало `set_current_stock`; запись StockRecord делает `apply_stock_bulk` пачкой.
    Возвращает StockPlan (если есть code_1c и stock) либо None.
    """
    if item.stock is None and item.reserved is None and item.available_stock is None:
        return None
    if item.stock is not None:
        product.stock_quantity = item.stock
    if item.reserved is not None:
        product.reserved_quantity = item.reserved
    available = _available_from(product, item)
    if available is not None:
        product.available_quantity = available
    product.recalc_stock_status()
    product.stock_updated_at = timezone.now()
    if product.code_1c and item.stock is not None:
        return StockPlan(
            product=product,
            code_1c=product.code_1c,
            warehouse=item.warehouse or "main",
            quantity=item.stock,
        )
    return None


def apply_stock_bulk(plans: list[StockPlan], *, batch_size: int = 1000) -> None:
    """Записать остатки пачкой: префетч существующих (code,warehouse) → split create/update.

    Дедуп по (code_1c, warehouse) last-wins (как update_or_create при дубле в батче).
    """
    by_key: dict[tuple[str, str], StockPlan] = {}
    for p in plans:
        by_key[(p.code_1c, p.warehouse)] = p  # last-wins
    if not by_key:
        return
    existing = {
        (r.code_1c, r.warehouse): r
        for r in StockRecord.objects.filter(code_1c__in={k[0] for k in by_key})
    }
    creates, updates = [], []
    for key, plan in by_key.items():
        rec = existing.get(key)
        if rec is None:
            creates.append(
                StockRecord(
                    product=plan.product,
                    code_1c=plan.code_1c,
                    warehouse=plan.warehouse,
                    quantity=plan.quantity,
                )
            )
        elif rec.quantity != plan.quantity or rec.product_id != plan.product.pk:
            rec.quantity = plan.quantity
            rec.product = plan.product
            updates.append(rec)
    if creates:
        StockRecord.objects.bulk_create(creates, batch_size=batch_size)
    if updates:
        StockRecord.objects.bulk_update(updates, ["quantity", "product"], batch_size=batch_size)
