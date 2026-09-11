"""Сборка фискального чека (54-ФЗ) из снимка заказа.

Чек уходит вместе с регистрацией платежа, и касса требует, чтобы **сумма позиций
до копейки совпала с суммой платежа** — иначе ``INVALID_RECEIPT_AMOUNT`` и заказ
не регистрируется вовсе. У нас между «суммой строк» и «суммой заказа» стоят промо
(скидка на товары и на доставку, #571), поэтому позиции считаются не из
``line_total``, а из него за вычетом скидки, и остаток копеек добивается в
последнюю позицию.

Второе ограничение: в позиции есть только цена за единицу и количество, поля
«сумма строки» нет. Если сумма со скидкой не делится нацело на количество
(1000.01 ₽ на 3 шт), позиция разбивается на две — ``qty-1`` по ровной цене и одна
штука с остатком. Так чек сходится и по строке, и по итогу.

Если свести чек с суммой платежа не удалось (расхождение больше нескольких
копеек — значит данные заказа противоречивы), поднимается ``ReceiptError``:
пробивать заведомо неверный чек нельзя, платёж не регистрируется, разбирается
менеджер.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings

from .client import to_kopecks, to_thousandths

logger = logging.getLogger(__name__)

#: Предел ФФД на наименование предмета расчёта (тег 1030).
MAX_NAME_LEN = 128

#: Единица измерения заказа → код АТОЛ (Таблица 3 документации).
MEASURE_CODES = {
    "шт": 0,
    "шт.": 0,
    "штука": 0,
    "уп": 0,
    "уп.": 0,
    "компл": 0,
    "компл.": 0,
    "набор": 0,
    "г": 1,
    "кг": 2,
    "т": 3,
    "см": 4,
    "дм": 5,
    "м": 6,
    "м2": 9,
    "кв.м": 9,
    "мл": 10,
    "л": 11,
    "м3": 12,
    "куб.м": 12,
}
DEFAULT_MEASURE = 0

#: Сколько копеек расхождения между позициями и суммой заказа считаем округлением.
#: Больше — это уже не округление, а рассогласование данных заказа.
ROUNDING_TOLERANCE = 10


class ReceiptError(ValueError):
    """Чек не удалось свести с суммой платежа."""


def measure_code(unit: str) -> int:
    return MEASURE_CODES.get((unit or "").strip().lower(), DEFAULT_MEASURE)


def _position(name: str, price: int, quantity: int, measure: int, subject: int) -> dict:
    return {
        "name": (name or "Товар")[:MAX_NAME_LEN],
        "price": price,
        "quantity": to_thousandths(quantity),
        "measure": measure,
        "paymentMethod": getattr(settings, "ATOLPAY_PAYMENT_METHOD_CODE", 0),
        "paymentSubject": subject,
        "tax": getattr(settings, "ATOLPAY_VAT_CODE", 0),
    }


def _split_by_unit_price(
    name: str, amount: int, quantity: int, measure: int, subject: int
) -> list[dict]:
    """Позиция с суммой ``amount`` копеек, разбитая так, чтобы цена×количество сошлись."""
    quantity = max(int(quantity), 1)
    if quantity == 1:
        return [_position(name, amount, 1, measure, subject)]

    unit_price, remainder = divmod(amount, quantity)
    if remainder == 0:
        return [_position(name, unit_price, quantity, measure, subject)]

    # Остаток кладём на одну штуку отдельной строкой: цена за единицу в ФФД целая.
    return [
        _position(name, unit_price, quantity - 1, measure, subject),
        _position(name, unit_price + remainder, 1, measure, subject),
    ]


def _items_amounts(order) -> list[tuple[object, int]]:
    """Суммы строк заказа в копейках, уже за вычетом промо-скидки."""
    rows = []
    for item in order.items.all():
        line = to_kopecks(item.line_total or Decimal("0"))
        promo = to_kopecks(item.promo_discount or Decimal("0"))
        rows.append([item, max(line - promo, 0)])

    # Скидка могла быть посчитана на заказ целиком (промокод), а не разложена по
    # строкам — тогда разводим остаток пропорционально суммам строк.
    declared = to_kopecks(order.items_discount_total or Decimal("0"))
    already = sum(to_kopecks(i.promo_discount or Decimal("0")) for i, _ in rows)
    gap = declared - already
    if gap > 0 and rows:
        total = sum(amount for _, amount in rows)
        left = gap
        for row in rows[:-1]:
            share = round(gap * row[1] / total) if total else 0
            share = min(share, row[1], left)
            row[1] -= share
            left -= share
        rows[-1][1] = max(rows[-1][1] - left, 0)

    return [(item, amount) for item, amount in rows]


def build_positions(order) -> list[dict]:
    """Позиции чека, сумма которых равна ``order.total`` в копейках."""
    goods_subject = getattr(settings, "ATOLPAY_SUBJECT_GOODS", 0)
    service_subject = getattr(settings, "ATOLPAY_SUBJECT_SERVICE", 3)
    target = to_kopecks(order.total)

    rows = _items_amounts(order)
    delivery = to_kopecks(order.delivery_cost or Decimal("0")) - to_kopecks(
        order.delivery_discount or Decimal("0")
    )
    delivery = max(delivery, 0)

    current = sum(amount for _, amount in rows) + delivery
    diff = target - current
    if diff and rows:
        # Расхождение округления добиваем в последнюю товарную позицию.
        if abs(diff) > ROUNDING_TOLERANCE:
            raise ReceiptError(
                f"Чек не сходится с суммой заказа {order.order_number}: "
                f"позиции {current} коп., заказ {target} коп."
            )
        item, amount = rows[-1]
        rows[-1] = (item, max(amount + diff, 0))
    elif diff and not rows:
        raise ReceiptError(f"Заказ {order.order_number} без позиций — чек не собрать")

    positions: list[dict] = []
    for item, amount in rows:
        if amount <= 0:
            # Подарок/100% скидка: нулевую позицию касса не примет, а на сумму
            # чека она не влияет — пропускаем.
            continue
        positions.extend(
            _split_by_unit_price(
                item.name,
                amount,
                item.quantity,
                measure_code(item.unit),
                goods_subject,
            )
        )

    if delivery > 0:
        positions.append(_position("Доставка", delivery, 1, DEFAULT_MEASURE, service_subject))

    if not positions:
        raise ReceiptError(f"Заказ {order.order_number}: в чеке не осталось позиций")

    check = sum(p["price"] * p["quantity"] // 1000 for p in positions)
    if check != target:
        raise ReceiptError(
            f"Чек заказа {order.order_number} не сошёлся после сборки: "
            f"{check} коп. вместо {target} коп."
        )
    return positions


def build_receipt(order) -> dict | None:
    """Блок ``receipt`` для регистрации платежа. ``None`` — фискализация выключена."""
    if not getattr(settings, "ATOLPAY_RECEIPT_ENABLED", True):
        return None

    receipt: dict = {
        "positions": build_positions(order),
        "providerId": getattr(settings, "ATOLPAY_RECEIPT_PROVIDER_ID", 100),
        "sno": getattr(settings, "ATOLPAY_SNO", 0),
        "type": "sell",
    }
    if order.customer_email:
        receipt["buyer"] = {"email": order.customer_email}
    return receipt
