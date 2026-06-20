"""Единый контракт ценообразования (ARCHITECTURE §4.1, ADR-0006).

Единственный способ получить цену товара — :func:`price_for`. Прямое чтение
``Product.price`` вне этого слоя запрещено: ``Product.price`` — кэш розницы,
``PriceRecord`` (pricing) — история и типы цен (опт), заказ хранит снимок цены.

Сейчас умеет выбирать розницу (B2C) и опт (B2B), считать скидку розницы и
отдавать стабильный результат. Промо/купоны/ступенчатые цены по qty и тип
``contract`` — задел на будущее (логики нет, но контракт зафиксирован).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.core.features import is_enabled

from .models import PriceRecord

RETAIL = "retail"
WHOLESALE = "wholesale"
CONTRACT = "contract"  # контракт-цены — задел, логики пока нет

_ZERO = Decimal("0")


@dataclass(frozen=True)
class PriceResult:
    """Результат расчёта цены — стабильный контракт для каталога/корзины/заказа."""

    base: Decimal | None
    final: Decimal | None
    currency: str
    discount: Decimal | None  # Decimal для retail; None для wholesale (нет опт-old_price)
    price_type: str

    @property
    def has_price(self) -> bool:
        return self.final is not None


def _wholesale_price(product) -> Decimal | None:
    """Текущая оптовая цена товара или None. Один запрос к PriceRecord."""
    if not product.code_1c:
        return None
    return (
        PriceRecord.objects.filter(
            code_1c=product.code_1c,
            price_type=WHOLESALE,
            currency=product.currency or "RUB",
            is_current=True,
        )
        .values_list("value", flat=True)
        .first()
    )


def price_for(product, user=None, qty: int = 1) -> PriceResult:
    """Цена товара для пользователя.

    Принимает ТОЛЬКО инстанс ``Product`` (не id: иначе скрытый запрос в цикле →
    N+1). Для id используйте :func:`price_for_id`. ``qty`` зарезервирован под
    ступенчатые цены (в MVP не влияет).
    """
    currency = product.currency or "RUB"

    # is_enabled('b2b') вызывается только для B2B-пользователя (short-circuit) —
    # для B2C/анонима оверхеда нет.
    if bool(user and getattr(user, "is_b2b", False)) and is_enabled("b2b"):
        wholesale = _wholesale_price(product)
        if wholesale is not None:
            return PriceResult(
                base=wholesale,
                final=wholesale,
                currency=currency,
                discount=None,
                price_type=WHOLESALE,
            )
        # опт не задан → фолбэк на розницу (иначе «цена по запросу» убьёт конверсию)

    base = product.price
    if base is None:
        return PriceResult(
            base=None, final=None, currency=currency, discount=_ZERO, price_type=RETAIL
        )

    discount = _ZERO
    if product.old_price is not None and product.old_price > base:
        discount = product.old_price - base
    return PriceResult(
        base=base, final=base, currency=currency, discount=discount, price_type=RETAIL
    )


def price_for_id(product_id: int, user=None, qty: int = 1) -> PriceResult:
    """Как :func:`price_for`, но по id — делает ОДИН запрос за товаром.

    Не использовать в циклах по списку товаров (там передавайте инстансы).
    """
    from apps.catalog.models import Product

    return price_for(Product.objects.get(pk=product_id), user=user, qty=qty)
