"""Реквизиты организации в аккаунте: ИНН, название, КПП.

Здесь — формат и минимальный набор, без которого организация не организация.
Счёт требует большего (юр. адрес, почта для отправки) — это проверяет
``apps.orders.invoice.validate_b2b_requisites``, переиспользуя отсюда формат.
Правило формата живёт в одном месте: слой заказов зависит от аккаунтов, а не
наоборот.
"""

from __future__ import annotations

import re

#: 10 цифр — организация, 12 — ИП.
INN_RE = re.compile(r"^\d{10}$|^\d{12}$")
KPP_RE = re.compile(r"^\d{9}$")


def is_legal_entity_inn(inn: str) -> bool:
    """ИНН из 10 цифр принадлежит организации; из 12 — предпринимателю."""
    return len((inn or "").strip()) == 10


def validate_company_requisites(inn: str, company_name: str, kpp: str = "") -> list[str]:
    """Проверить реквизиты организации. Пустой список — всё в порядке.

    КПП есть только у организаций: у ИП его не существует, поэтому при ИНН из
    12 цифр он необязателен, но если указан — проверяется формат.
    """
    errors: list[str] = []
    inn = (inn or "").strip()
    company_name = (company_name or "").strip()
    kpp = (kpp or "").strip()

    legal_entity = False
    if not inn:
        errors.append("Укажите ИНН организации.")
    elif not INN_RE.match(inn):
        errors.append("ИНН должен содержать 10 или 12 цифр.")
    else:
        legal_entity = is_legal_entity_inn(inn)

    if not company_name:
        errors.append("Укажите название организации.")

    if legal_entity and not kpp:
        errors.append("КПП обязателен для юридического лица.")
    elif kpp and not KPP_RE.match(kpp):
        errors.append("КПП должен содержать 9 цифр.")

    return errors
