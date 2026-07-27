"""Подготовка данных счёта для B2B-заказов (#53).

Счёт формируется из снимка заказа (buyer) и SiteSettings (seller).
Фактическая генерация PDF/печатной формы — задача фронтенда или отдельного модуля.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.accounts.models import CustomerType


@dataclass(frozen=True)
class InvoiceItem:
    name: str
    article: str
    unit: str
    quantity: int
    price: Decimal
    total: Decimal


@dataclass(frozen=True)
class InvoiceData:
    order_number: str
    date: date
    seller: dict
    buyer: dict
    items: list[InvoiceItem] = field(default_factory=list)
    total: Decimal = Decimal("0.00")
    currency: str = "RUB"
    # #430 (M-06): выделенный НДС из снимка заказа.
    vat_rate: int = 0
    vat_amount: Decimal = Decimal("0.00")
    amount_without_vat: Decimal = Decimal("0.00")
    # #429 (M-05): доставка отдельной строкой. delivery_cost=None + delivery_pending
    # → стоимость определяется менеджером; счёт предварительный (pending_delivery_quote),
    # финальный счёт не выпускается до ввода стоимости.
    delivery_cost: Decimal | None = None
    delivery_pending: bool = False
    # #571: скидка по акциям/промокоду — отдельной строкой, чтобы счёт сходился
    # арифметически: сумма строк − скидка (+ доставка) == итог.
    items_discount_total: Decimal = Decimal("0.00")
    promo_code: str = ""

    @property
    def status(self) -> str:
        return "pending_delivery_quote" if self.delivery_pending else "issued"


_INN_RE = re.compile(r"^\d{10}$|^\d{12}$")
_KPP_RE = re.compile(r"^\d{9}$")


def validate_b2b_requisites(
    inn: str,
    company_name: str,
    kpp: str = "",
    legal_address: str = "",
    email: str = "",
) -> list[str]:
    """Проверить реквизиты B2B (ADR #444). Вернуть список ошибок (пустой = ок).

    ИНН 10 цифр → юрлицо: КПП обязателен (9 цифр). ИНН 12 цифр → ИП: КПП
    необязателен, но при наличии проверяется формат. Юр.адрес и email (для
    отправки счёта) обязательны.
    """
    errors = []
    inn = (inn or "").strip()
    company_name = (company_name or "").strip()
    kpp = (kpp or "").strip()
    legal_address = (legal_address or "").strip()
    email = (email or "").strip()

    is_legal_entity = False
    if not inn:
        errors.append("ИНН обязателен для B2B-заказа.")
    elif not _INN_RE.match(inn):
        errors.append("ИНН должен содержать 10 или 12 цифр.")
    else:
        is_legal_entity = len(inn) == 10

    if not company_name:
        errors.append("Название организации обязательно для B2B-заказа.")

    # КПП обязателен для юрлица (ИНН 10); для ИП (ИНН 12) — опционален.
    if is_legal_entity and not kpp:
        errors.append("КПП обязателен для юридического лица.")
    elif kpp and not _KPP_RE.match(kpp):
        errors.append("КПП должен содержать 9 цифр.")

    if not legal_address:
        errors.append("Юридический адрес обязателен для B2B-заказа.")

    if not email:
        errors.append("Email обязателен для отправки счёта.")

    return errors


def prepare_invoice(order) -> InvoiceData:
    """Собрать данные счёта из снимка заказа и SiteSettings."""
    from apps.core.models import SiteSettings

    settings = SiteSettings.get_solo()

    items = [
        InvoiceItem(
            name=oi.name,
            article=oi.article,
            unit=oi.unit,
            quantity=oi.quantity,
            price=oi.price_final,
            total=oi.line_total,
        )
        for oi in order.items.all()
    ]

    return InvoiceData(
        order_number=order.order_number,
        date=order.created_at.date(),
        seller=settings.requisites or {},
        buyer={
            "company_name": order.company_name,
            "inn": order.inn,
            "kpp": order.kpp,
            "legal_address": order.legal_address,
        },
        items=items,
        total=order.total,
        currency=order.currency,
        vat_rate=order.vat_rate,
        vat_amount=order.vat_amount,
        amount_without_vat=order.amount_without_vat,
        delivery_cost=order.delivery_cost,
        delivery_pending=order.delivery_calc_status == "manual_required",
        items_discount_total=order.items_discount_total,
        promo_code=order.promo_code,
    )


def prepare_b2b_order(order) -> InvoiceData:
    """Обёртка: проверить что заказ B2B, затем подготовить счёт."""
    if order.customer_type != CustomerType.B2B:
        raise ValueError("Счёт выставляется только для B2B-заказов.")
    return prepare_invoice(order)
