"""Нормализация сырых строк 1С в стабильный DTO `Item`.

Парсер (`parsers.py`) отдаёт строки «как есть»: разные кодировки и разные
названия колонок (рус. заголовки CSV из 1С, либо канонические ключи из API).
Здесь они приводятся к единому `Item`, на котором работают matching / writer /
pricing / stock.

Важно: `Item` НЕ хранит raw/transport-данные — пару `(raw, item)` держит
`use_cases.py`. `row_hash(raw)` считается от исходного payload (трассировка:
«что реально пришло из 1С»).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


def _norm_key(key: Any) -> str:
    """Канонизировать имя колонки: нижний регистр, без пробелов/подчёркиваний/дефисов."""
    return str(key).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


# Для каждого поля DTO — принимаемые имена-источники (уже в форме _norm_key).
# Расширяется под новые форматы 1С, не трогая importer/use_cases (OCP).
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "code_1c": ("externalid", "code1c", "код", "код1с", "кодноменклатуры"),
    "article": ("sku", "article", "артикул"),
    "barcode": ("barcode", "штрихкод"),
    "name": ("name", "наименование", "название"),
    "brand": ("brand", "бренд", "производитель"),
    "unit": ("unit", "ед", "едизм", "единица", "единицаизмерения"),
    "source_group": ("sourcegroup", "группа", "исходнаягруппа"),
    "is_active": ("isactive", "активность", "активен"),
    "price": ("price", "цена"),
    "old_price": ("oldprice", "стараяцена"),
    "currency": ("currency", "валюта"),
    "stock": ("stock", "остаток", "количество", "колво"),
    "reserved": ("reserved", "резерв"),
    "available_stock": ("availablestock", "доступно", "доступныйостаток"),
    "warehouse": ("warehouse", "склад"),
    "price_type": ("pricetype", "типцены"),
}

_DECIMAL_FIELDS = {"price", "old_price", "stock", "reserved", "available_stock"}
_STRING_FIELDS = {
    "code_1c",
    "article",
    "barcode",
    "name",
    "brand",
    "unit",
    "source_group",
    "currency",
    "warehouse",
    "price_type",
}


def to_decimal(value) -> Decimal | None:
    """Разобрать число из 1С (деньги/остаток), различая роль `,`/`.`/пробела.

    1С 7.7 шлёт число строкой в разном формате. Слепой `.replace(",", ".")` либо
    ронял строку в `None` (skipped), либо занижал цену в 1000× (#271). Правило:

    * пробел — всегда разделитель тысяч (выкидываем);
    * два разных разделителя — последний по позиции отделяет дробь, другой тысячи
      (`"1.234,50"`→1234.50, `"1,234.50"`→1234.50);
    * одиночный разделитель + ровно 3 цифры после — тысячи (`"1,234"`→1234), НО
      ведущий 0 в целой части ⇒ дробь (`"0,500"`→0.5);
    * одиночный разделитель + не 3 цифры — дробь (`"1234,50"`→1234.50);
    * повтор одного разделителя — группировка тысяч (`"1,234,567"`→1234567).
    """
    if value is None or value == "":
        return None
    # Числовые типы — без строкового разбора разделителей (иначе float-repr врёт).
    if isinstance(value, int | float | Decimal):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    s = str(value).strip().replace(" ", "")  # пробел = тысячи
    if not s:
        return None
    sign = ""
    if s[:1] in "+-":
        sign, s = s[0], s[1:]

    has_comma = "," in s
    has_dot = "." in s
    if has_comma and has_dot:
        # Последний по позиции разделитель — десятичный, другой — тысячи.
        dec, tho = (",", ".") if s.rfind(",") > s.rfind(".") else (".", ",")
        s = s.replace(tho, "").replace(dec, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        if s.count(sep) > 1:
            s = s.replace(sep, "")  # повтор ⇒ тысячи
        else:
            int_part, frac_part = s.split(sep)
            if len(frac_part) == 3 and int_part and not int_part.startswith("0"):
                s = s.replace(sep, "")  # 3 цифры + не ведущий 0 ⇒ тысячи
            else:
                s = s.replace(sep, ".")  # иначе ⇒ дробь

    try:
        return Decimal(sign + s)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("1", "true", "да", "yes", "y", "истина", "+"):
        return True
    if s in ("0", "false", "нет", "no", "n", "ложь", "-"):
        return False
    return None


def row_hash(raw: Mapping[str, Any]) -> str:
    """SHA-256 от исходной строки (для трассировки и выявления повторов)."""
    payload = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Item:
    """Нормализованная строка 1С. Без raw/transport."""

    code_1c: str = ""
    article: str = ""
    barcode: str = ""
    name: str = ""
    brand: str = ""
    unit: str = ""
    source_group: str = ""
    is_active: bool | None = None
    price: Decimal | None = None
    old_price: Decimal | None = None
    currency: str = ""
    stock: Decimal | None = None
    reserved: Decimal | None = None
    available_stock: Decimal | None = None
    warehouse: str = ""
    price_type: str = ""

    @property
    def has_identifier(self) -> bool:
        return bool(self.code_1c or self.article)


def normalize_item(raw: Mapping[str, Any]) -> Item:
    """Привести сырую строку к `Item` (по COLUMN_ALIASES)."""
    lut = {_norm_key(k): v for k, v in raw.items()}

    def pick(field: str):
        for src in COLUMN_ALIASES[field]:
            if src in lut and lut[src] not in (None, ""):
                return lut[src]
        return None

    data: dict[str, Any] = {}
    for field in _STRING_FIELDS:
        value = pick(field)
        data[field] = "" if value is None else str(value).strip()
    for field in _DECIMAL_FIELDS:
        data[field] = to_decimal(pick(field))
    data["is_active"] = _to_bool(pick("is_active"))
    return Item(**data)


def normalize_items(raw_items: list[Mapping[str, Any]]) -> list[Item]:
    return [normalize_item(raw) for raw in raw_items]
