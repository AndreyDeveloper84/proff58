"""Расчёт НДС из суммы, включающей налог (#430, M-06).

Контракт (ADR-0013, #444, Wave 1 — ``docs/adr/ADR-0013-b2b-vat-delivery-contract.md``):
цена всегда включает НДС. По сумме с НДС считаем
выделенный налог и сумму без НДС:

    НДС = сумма_с_НДС × rate / (100 + rate)

Расчёт на Decimal с округлением до копеек (ROUND_HALF_UP). Сумма без НДС —
остаток (сумма_с_НДС − НДС), чтобы без+налог всегда давали ровно сумму с НДС.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")


def vat_breakdown(gross: Decimal, rate_percent: int) -> tuple[Decimal, Decimal]:
    """Разложить сумму с НДС на (без_НДС, сумма_НДС).

    ``gross`` — сумма, включающая НДС; ``rate_percent`` — ставка (напр. 22).
    Нулевая ставка/сумма → (gross, 0). Возвращает суммы, округлённые до копеек;
    инвариант: без_НДС + сумма_НДС == round(gross).
    """
    gross = Decimal(gross).quantize(_CENTS, rounding=ROUND_HALF_UP)
    if rate_percent <= 0 or gross == 0:
        return gross, Decimal("0.00")
    rate = Decimal(rate_percent)
    vat = (gross * rate / (Decimal(100) + rate)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    net = gross - vat
    return net, vat
