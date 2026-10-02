"""Остатки: денормализация в Product + запись StockRecord по складу.

Чьи поля (DRF-2737):

- ``stock_quantity`` — физический остаток, мастер — 1С;
- ``reserved_quantity`` — удержано под неоплаченные заказы САЙТА. Этот счётчик ведёт
  только приложение заказов (оформление, правка состава, ``orders/reservation.py``) —
  через ``F()``, под замком строки товара. Обмен его не пишет никогда: раньше ``reserved`` из 1С и значение из устаревшего
  инстанса затирали удержание параллельного чекаута — товар продавался дважды;
- ``available_quantity`` — производное: его меняют и сайт (чекаут, отмена), и обмен.
  Поэтому обмен считает его от СВЕЖЕГО ``reserved_quantity``: товар для записи
  остатка читается под ``select_for_update`` (``locked``) прямо перед расчётом.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product

from . import matching
from .models import StockRecord
from .normalizers import Item

#: Поля, которые пишет обмен остатками. ``reserved_quantity`` здесь нет намеренно.
_STOCK_FIELDS = [
    "stock_quantity",
    "available_quantity",
    "stock_status",
    "stock_updated_at",
]

_ZERO = Decimal("0")

logger = logging.getLogger(__name__)


def locked(product_id: int) -> Product:
    """Свежая строка товара под замком — для записи остатка. Только внутри транзакции.

    ``NO KEY UPDATE``: взаимное исключение с чекаутом (он берёт ``FOR UPDATE``) и с
    ``UPDATE … F()`` резерва сохраняется, а вставкам со ссылкой на товар (корзина,
    избранное, характеристики, история цены) замок не мешает.

    Порядок замков: обмен берёт одну строку товара за транзакцию (либо пачку по
    возрастанию pk), чекаут — товары по возрастанию pk. Цикла ожидания нет — пока
    вызывающий не обёрнут во внешнюю транзакцию на весь батч (``ATOMIC_REQUESTS``
    для ручек обмена включать нельзя: замки копились бы в порядке строк файла).
    """
    return Product.objects.select_for_update(no_key=True).get(pk=product_id)


def has_stock(item: Item) -> bool:
    """Есть ли в строке остаток, который можно записать.

    Одного ``reserved`` мало: резерв 1С сайт не хранит (счётчик ``reserved_quantity``
    — про заказы сайта), он имеет смысл только рядом со ``stock`` в той же строке.
    """
    return item.stock is not None or item.available_stock is not None


def _available_from(product: Product, item: Item) -> Decimal | None:
    """Свободный остаток по данным 1С, зажатый в ноль. None — данных нет.

    Свободно то, что свободно по данным 1С, минус удержанное под неоплаченные заказы
    сайта: 1С о них ещё не знает. «По данным 1С» — явный ``available_stock`` либо
    ``stock`` минус её собственный резерв (если прислан). Раньше явное число писалось
    как есть, а ненулевой ``reserved`` из 1С подменял резерв сайта — в обоих случаях
    товар под свежим заказом снова выходил в продажу (DRF-2737). Если 1С уже учла
    тот же заказ в своём резерве, он вычтется дважды — ошибка в безопасную сторону.
    ``product`` обязан быть свежим (см. ``locked``): резерв сайта меняется чекаутом.

    1С может прислать резерв больше остатка (или прямо отрицательный `available`).
    Минус в `available_quantity` запрещён constraint'ом (DRF-1003), а ронять из-за
    одной такой строки весь пакетный обмен нельзя — поэтому зажимаем, а не падаем.
    """
    if item.available_stock is not None:
        base = item.available_stock
    elif item.stock is not None:
        base = item.stock - max(_ZERO, item.reserved or _ZERO)
    else:
        return None
    value = base - max(_ZERO, product.reserved_quantity or _ZERO)
    if value < _ZERO <= base:
        # В минус уводит именно резерв сайта: под заказами удержано больше, чем есть
        # по данным 1С. «Резерв 1С больше остатка» — обычное дело, о нём не шумим.
        logger.warning(
            "1С: под заказами сайта удержано больше, чем есть у товара %s (%s) — записан ноль",
            product.code_1c or product.pk,
            value,
        )
    return max(_ZERO, value)


def set_current_stock(product: Product, item: Item) -> bool:
    """Записать остаток в Product и StockRecord по складу. Не сохраняет Product."""
    if not has_stock(item):
        return False

    warehouse = item.warehouse or "main"

    if item.stock is not None:
        product.stock_quantity = item.stock
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
    """Точечно применить остаток к найденному товару (find-first). Вызывается только из тестов."""
    found = matching.find_product(item)
    if found is None:
        return False
    with transaction.atomic():
        product = locked(found.pk)
        if not set_current_stock(product, item):
            return False
        product.save(update_fields=[*_STOCK_FIELDS, "updated_at"])
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
    if not has_stock(item):
        return None
    if item.stock is not None:
        product.stock_quantity = item.stock
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
