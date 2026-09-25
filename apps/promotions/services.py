"""Расчёт скидок (#571) — единственная точка правды по промо.

`compute_promotions` — детерминированная функция: одна и та же корзина +
промокод → один и тот же breakdown. Деньги только `Decimal` (quantize 0.01,
HALF_UP); ни строка, ни итог не могут уйти ниже нуля.

Правила совмещения (MVP, зафиксированы тестами):
- на строку — РОВНО ОДНА строчная скидка, лучшая по сумме (кандидаты: автоакции
  scope=product|category + промокод-акция с тем же scope); тай-брейк:
  сумма DESC → priority DESC → id ASC;
- промокод scope=cart применяется ПОВЕРХ строчных скидок (к остатку);
- free_delivery — кодовая награда: скидка = стоимость рассчитанной B2C-доставки
  (quote не меняется — это отдельная discount-строка);
- валидный код без выгоды → ``code_error.not_beneficial`` (не блокирует заказ).

Вызывающий (apps.orders) собирает входные строки сам и передаёт контекст
доставки, когда он известен (place_order/чекаут); в корзине доставки ещё нет —
``delivery_status=""`` и free_delivery-код просто ждёт оформления.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import DiscountType, PromoScope, Promotion

_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")

# Человеческие тексты ошибок промокода (issue #571 + not_beneficial).
CODE_ERRORS = {
    "not_found": "Такого промокода нет.",
    "not_available": "Промокод сейчас не действует.",
    "expired": "Срок действия промокода истёк.",
    "not_applicable": "Промокод не подходит к товарам в корзине.",
    "not_beneficial": (
        "Промокод сейчас не даёт дополнительной выгоды — применена более выгодная акция."
    ),
}


@dataclass(frozen=True)
class PromoLineInput:
    """Строка корзины/заказа для расчёта. ``key`` — id строки у вызывающего."""

    key: int
    product_id: int
    quantity: int
    line_total: Decimal


@dataclass(frozen=True)
class AppliedPromo:
    promotion_id: int
    name: str
    discount_type: str
    scope: str
    promo_code: str
    amount: Decimal


@dataclass(frozen=True)
class CodeError:
    code: str
    message: str


@dataclass(frozen=True)
class PromoBreakdown:
    line_discounts: dict[int, Decimal] = field(default_factory=dict)
    items_discount_total: Decimal = _ZERO
    delivery_discount: Decimal = _ZERO
    applied: list[AppliedPromo] = field(default_factory=list)
    code_error: CodeError | None = None


EMPTY_BREAKDOWN = PromoBreakdown()


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def resolve_promo_code(code: str, now=None) -> tuple[Promotion | None, CodeError | None]:
    """Найти акцию по коду с точной причиной отказа (для человеческой ошибки)."""
    code = (code or "").strip()
    if not code:
        return None, None
    now = now or timezone.now()
    promo = Promotion.objects.filter(promo_code__iexact=code).first()
    if promo is None:
        return None, CodeError("not_found", CODE_ERRORS["not_found"])
    if not promo.is_active or (promo.starts_at and promo.starts_at > now):
        return None, CodeError("not_available", CODE_ERRORS["not_available"])
    if promo.ends_at and promo.ends_at <= now:
        return None, CodeError("expired", CODE_ERRORS["expired"])
    return promo, None


def _active_auto_promotions(now):
    return list(
        Promotion.objects.filter(is_active=True, promo_code="")
        .filter(_window_q(now))
        .exclude(discount_type=DiscountType.FREE_DELIVERY)
        .prefetch_related("products", "categories")
    )


def _window_q(now):
    from django.db.models import Q

    return (Q(starts_at__isnull=True) | Q(starts_at__lte=now)) & (
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    )


def _category_paths(product_ids) -> dict[int, str]:
    """product_id → path его категории (treebeard MP_Node). Один запрос."""
    from apps.catalog.models import Product

    rows = Product.objects.filter(id__in=product_ids).values("id", "category__path")
    return {r["id"]: r["category__path"] or "" for r in rows}


def _matches(promo: Promotion, product_id: int, product_path: str) -> bool:
    """Подходит ли товарная/категорийная акция к строке."""
    if promo.scope == PromoScope.PRODUCT:
        return any(p.pk == product_id for p in promo.products.all())
    if promo.scope == PromoScope.CATEGORY:
        # Поддерево: path категории товара начинается с path категории акции.
        if not product_path:
            return False
        return any(product_path.startswith(c.path) for c in promo.categories.all() if c.path)
    return False


def _line_amount(promo: Promotion, line: PromoLineInput) -> Decimal:
    if promo.discount_type == DiscountType.PERCENT:
        amount = line.line_total * promo.discount_value / Decimal("100")
    elif promo.discount_type == DiscountType.FIXED:
        amount = promo.discount_value * line.quantity
    else:  # free_delivery к строкам не применяется
        return _ZERO
    return min(_q(amount), line.line_total)


def compute_promotions(
    lines: list[PromoLineInput],
    *,
    promo_code: str = "",
    customer_type: str = "b2c",
    delivery_cost: Decimal | None = None,
    delivery_status: str = "",
    now=None,
) -> PromoBreakdown:
    """Посчитать скидки для набора строк.

    ``delivery_status``/``delivery_cost`` передаются, когда доставка уже
    рассчитана (place_order); пустой статус = контекст корзины, free_delivery
    ждёт оформления и не считается «бесполезным».
    """
    now = now or timezone.now()
    code_promo, code_error = resolve_promo_code(promo_code, now)
    if not lines and code_promo is None:
        return PromoBreakdown(code_error=code_error)

    auto = _active_auto_promotions(now)
    paths = _category_paths([ln.product_id for ln in lines]) if lines else {}

    line_discounts: dict[int, Decimal] = {}
    per_promo_amount: dict[int, Decimal] = {}
    code_contribution = _ZERO

    # --- строчные скидки: best-of на строку ---
    line_candidates = auto
    if code_promo is not None and code_promo.scope in (PromoScope.PRODUCT, PromoScope.CATEGORY):
        line_candidates = auto + [code_promo]
    for line in lines:
        best: tuple[Decimal, int, int, Promotion] | None = (
            None  # (amount, prio, -id) через сравнение
        )
        for promo in line_candidates:
            if not _matches(promo, line.product_id, paths.get(line.product_id, "")):
                continue
            amount = _line_amount(promo, line)
            if amount <= 0:
                continue
            rank = (amount, promo.priority, -promo.pk)
            if best is None or rank > (best[0], best[1], best[2]):
                best = (amount, promo.priority, -promo.pk, promo)
        if best is None:
            continue
        amount, _prio, _nid, promo = best
        line_discounts[line.key] = amount
        per_promo_amount[promo.pk] = per_promo_amount.get(promo.pk, _ZERO) + amount
        if code_promo is not None and promo.pk == code_promo.pk:
            code_contribution += amount

    items_discount_total = _q(sum(line_discounts.values(), _ZERO))
    subtotal_after_lines = sum((ln.line_total for ln in lines), _ZERO) - items_discount_total

    # --- промокод scope=cart: поверх строчных ---
    if code_promo is not None and code_promo.scope == PromoScope.CART:
        if code_promo.discount_type == DiscountType.PERCENT:
            amount = _q(subtotal_after_lines * code_promo.discount_value / Decimal("100"))
        elif code_promo.discount_type == DiscountType.FIXED:
            amount = min(_q(code_promo.discount_value), subtotal_after_lines)
        else:
            amount = _ZERO  # free_delivery — ниже, отдельной строкой доставки
        amount = max(amount, _ZERO)
        if amount > 0:
            per_promo_amount[code_promo.pk] = per_promo_amount.get(code_promo.pk, _ZERO) + amount
            items_discount_total = _q(items_discount_total + amount)
            code_contribution += amount

    # --- free_delivery: скидка на рассчитанную B2C-доставку ---
    delivery_discount = _ZERO
    delivery_known = bool(delivery_status)
    if (
        code_promo is not None
        and code_promo.discount_type == DiscountType.FREE_DELIVERY
        and customer_type != "b2b"
        and delivery_status == "calculated"
        and delivery_cost
        and delivery_cost > 0
    ):
        delivery_discount = _q(delivery_cost)
        per_promo_amount[code_promo.pk] = (
            per_promo_amount.get(code_promo.pk, _ZERO) + delivery_discount
        )
        code_contribution += delivery_discount

    # --- валидный код без выгоды (контекст доставки известен) ---
    if (
        code_promo is not None
        and code_error is None
        and code_contribution <= 0
        and (code_promo.discount_type != DiscountType.FREE_DELIVERY or delivery_known)
    ):
        if code_promo.scope in (PromoScope.PRODUCT, PromoScope.CATEGORY) and not any(
            _matches(code_promo, ln.product_id, paths.get(ln.product_id, "")) for ln in lines
        ):
            code_error = CodeError("not_applicable", CODE_ERRORS["not_applicable"])
        else:
            code_error = CodeError("not_beneficial", CODE_ERRORS["not_beneficial"])

    # --- applied: детерминированный порядок (по id акции) ---
    by_id = {p.pk: p for p in auto}
    if code_promo is not None:
        by_id[code_promo.pk] = code_promo
    applied = [
        AppliedPromo(
            promotion_id=pk,
            name=by_id[pk].name,
            discount_type=by_id[pk].discount_type,
            scope=by_id[pk].scope,
            promo_code=by_id[pk].promo_code,
            amount=_q(amount),
        )
        for pk, amount in sorted(per_promo_amount.items())
        if amount > 0
    ]
    # free_delivery-код в корзине (доставка ещё не известна): показываем как
    # применённый с amount=0 — «применится при оформлении».
    if (
        code_promo is not None
        and code_error is None
        and code_promo.discount_type == DiscountType.FREE_DELIVERY
        and not delivery_known
        and code_promo.pk not in per_promo_amount
    ):
        applied.append(
            AppliedPromo(
                promotion_id=code_promo.pk,
                name=code_promo.name,
                discount_type=code_promo.discount_type,
                scope=code_promo.scope,
                promo_code=code_promo.promo_code,
                amount=_ZERO,
            )
        )

    return PromoBreakdown(
        line_discounts=line_discounts,
        items_discount_total=items_discount_total,
        delivery_discount=delivery_discount,
        applied=applied,
        code_error=code_error,
    )
