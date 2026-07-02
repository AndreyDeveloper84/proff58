"""Нормализация телефонных номеров (#421 / B-01).

Единый канонический формат для матчинга: телефон приводится к ``+7XXXXXXXXXX``
для российских номеров. Используется при регистрации, входе, привязке MAX и при
claim гостевых заказов — чтобы разные форматы одного номера не расходились.
"""

from __future__ import annotations

import re


def normalize_phone(raw: str) -> str:
    """Привести номер к каноническому виду ``+<digits>``.

    Российские номера (10 цифр, либо 11 цифр с ведущей 7/8) → ``+7XXXXXXXXXX``.
    Прочие — ``+`` перед оставшимися цифрами. Пустой/без цифр вход → ``""``.
    Функция идемпотентна: normalize(normalize(x)) == normalize(x).
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return "+" + digits
