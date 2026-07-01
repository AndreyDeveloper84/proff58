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


def _wholesale_result(product, wholesale: Decimal, currency: str) -> PriceResult:
    """PriceResult для опта. Единый источник формы опт-результата."""
    return PriceResult(
        base=wholesale,
        final=wholesale,
        currency=currency,
        discount=None,
        price_type=WHOLESALE,
    )


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
    :func:`price_map_for_products` (bulk, без N+1 по опт-ценам). ``qty``
    зарезервирован под ступенчатые цены (в MVP не влияет).
    """
    currency = product.currency or "RUB"

    # Опт — только верифицированным B2B (#340): is_b2b_verified проверяет
    # и customer_type, и profile.is_b2b_verified. is_enabled('b2b') вызывается
    # после short-circuit, чтобы B2C/аноним не платил за feature-check.
    if bool(user and getattr(user, "is_b2b_verified", False)) and is_enabled("b2b"):
        wholesale = _wholesale_price(product)
        if wholesale is not None:
            return _wholesale_result(product, wholesale, currency)
        # опт не задан → фолбэк на розницу (иначе «цена по запросу» убьёт конверсию)

    return _retail_result(product, currency)


def price_map_for_products(products, user=None) -> dict[int, PriceResult]:
    """Bulk-резолвер цен: ``product.pk -> PriceResult`` без N+1 по опт-ценам.

    Семантика для каждого товара совпадает с поэлементным
    :func:`price_for(product, user) <price_for>`:

    * B2C/аноним (не b2b) — розница в памяти (``_retail_result``), без запросов
      к ``PriceRecord``.
    * B2B (и фича ``b2b`` включена) — ОДНИМ запросом подтягиваем текущие опт-цены
      по ``code_1c`` всех товаров (где он непустой), сопоставляем по
      ``(code_1c, currency)`` как в :func:`_wholesale_price`. Есть опт →
      ``_wholesale_result``; нет опт-цены ИЛИ пустой ``code_1c`` → фолбэк на
      розницу ``_retail_result``.
    """
    products = list(products)
    is_b2b = bool(user and getattr(user, "is_b2b_verified", False)) and is_enabled("b2b")

    if not is_b2b:
        return {p.pk: _retail_result(p, p.currency or "RUB") for p in products}

    codes = [p.code_1c for p in products if p.code_1c]
    # Ключ сопоставления — (code_1c, currency): на эту пару ровно одна current.
    wholesale_by_key: dict[tuple[str, str], Decimal] = {}
    if codes:
        for code_1c, currency, value in PriceRecord.objects.filter(
            code_1c__in=codes,
            price_type=WHOLESALE,
            is_current=True,
        ).values_list("code_1c", "currency", "value"):
            wholesale_by_key[(code_1c, currency)] = value

    result: dict[int, PriceResult] = {}
    for p in products:
        currency = p.currency or "RUB"
        wholesale = wholesale_by_key.get((p.code_1c, currency)) if p.code_1c else None
        if wholesale is not None:
            result[p.pk] = _wholesale_result(p, wholesale, currency)
        else:
            result[p.pk] = _retail_result(p, currency)
    return result


def price_for_id(product_id: int, user=None, qty: int = 1) -> PriceResult:
    """Как :func:`price_for`, но по id — делает ОДИН запрос за товаром.

    Не использовать в циклах по списку товаров (там передавайте инстансы).
    """
    from apps.catalog.models import Product

    return price_for(Product.objects.get(pk=product_id), user=user, qty=qty)
