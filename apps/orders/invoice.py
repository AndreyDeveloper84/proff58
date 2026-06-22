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


_INN_RE = re.compile(r"^\d{10}$|^\d{12}$")


def validate_b2b_requisites(inn: str, company_name: str) -> list[str]:
    """Проверить реквизиты B2B. Вернуть список ошибок (пустой = ок)."""
    errors = []
    inn = (inn or "").strip()
    company_name = (company_name or "").strip()

    if not inn:
        errors.append("ИНН обязателен для B2B-заказа.")
    elif not _INN_RE.match(inn):
        errors.append("ИНН должен содержать 10 или 12 цифр.")

    if not company_name:
        errors.append("Название организации обязательно для B2B-заказа.")

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
    )


def prepare_b2b_order(order) -> InvoiceData:
    """Обёртка: проверить что заказ B2B, затем подготовить счёт."""
    if order.customer_type != CustomerType.B2B:
        raise ValueError("Счёт выставляется только для B2B-заказов.")
    return prepare_invoice(order)
