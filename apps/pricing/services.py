"""Единый контракт ценообразования (ARCHITECTURE §4.1, ADR-0006).

Единственный способ получить цену товара — :func:`price_for`. Прямое чтение
``Product.price`` вне этого слоя запрещено: ``Product.price`` — кэш розницы,
``PriceRecord`` (pricing) — история типов цен из 1С, заказ хранит снимок цены.

#430 (M-06, ADR #444): единый ценник — числовая цена одинакова для B2C и B2B,
отдельной оптовой цены нет. НДС для B2B выделяется отдельно (см. ``pricing.vat``),
не меняя числовую цену. Промо/купоны/ступенчатые цены и тип ``contract`` — задел
на будущее (логики нет).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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


def _retail_result(product, currency: str) -> PriceResult:
    """PriceResult из розницы (base=product.price, скидка от old_price).

    Единый источник формы розничного результата для price_for и bulk-резолвера —
    формула скидки не дублируется.
    """
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


def price_for(product, user=None, qty: int = 1) -> PriceResult:
    """Цена товара для пользователя.

    Принимает ТОЛЬКО инстанс ``Product`` (не id: иначе скрытый запрос в цикле →
    N+1). Для id используйте :func:`price_for_id`. Для списка товаров используйте
    :func:`price_map_for_products` (bulk). ``qty`` зарезервирован под ступенчатые
    цены (в MVP не влияет).

    #430 (M-06, ADR #444): единый ценник — числовая цена одинакова для B2C и B2B,
    отдельной оптовой цены нет. НДС для B2B выделяется отдельно (см. pricing.vat),
    но не меняет числовую цену. Параметр ``user`` сохранён в сигнатуре для
    совместимости и будущих правил (промо/контракт-цены).
    """
    currency = product.currency or "RUB"
    return _retail_result(product, currency)


def price_map_for_products(products, user=None) -> dict[int, PriceResult]:
    """Bulk-резолвер цен: ``product.pk -> PriceResult``.

    #430 (M-06, ADR #444): единый ценник для B2C и B2B — розница в памяти, без
    запросов к ``PriceRecord``. Семантика совпадает с :func:`price_for`.
    """
    return {p.pk: _retail_result(p, p.currency or "RUB") for p in products}


def price_for_id(product_id: int, user=None, qty: int = 1) -> PriceResult:
    """Как :func:`price_for`, но по id — делает ОДИН запрос за товаром.

    Не использовать в циклах по списку товаров (там передавайте инстансы).
    """
    from apps.catalog.models import Product

    return price_for(Product.objects.get(pk=product_id), user=user, qty=qty)
