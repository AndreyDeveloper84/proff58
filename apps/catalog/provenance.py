# apps/catalog/provenance.py
"""Единый резолвер провенанса и применение «найденного» значения к каталогу.

Catalog-owned контракт: apps/ai передаёт нейтральный SourcedValueCommand, каталог
ничего не знает о ContentFinding. Карта приоритетов — единственная, из
data/attribute_rules.json (source_priority)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import Attribute, AttributeType, Product, ProductAttributeValue
from .read_models import rebuild_attrs_cache

_TEXT_TARGETS = {"name", "short_description", "description"}


@lru_cache(maxsize=1)
def _priority_map() -> dict[str, int]:
    path = Path(settings.BASE_DIR) / "data" / "attribute_rules.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("source_priority", {})


def can_overwrite(new: str, existing: str, *, allow_equal: bool = False) -> bool:
    """Авто: строго priority(new) > priority(existing). Пустой existing → True.
    allow_equal=True (явное решение модератора) разрешает равный приоритет."""
    if not existing:
        return True
    pm = _priority_map()
    pn, pe = pm.get(new, 0), pm.get(existing, 0)
    return pn > pe or (allow_equal and pn == pe and pn > 0)


def value_hash(value) -> str:
    """Стабильный хеш текущего значения поля для baseline-сверки. None/'' → хеш ''."""
    return hashlib.sha256(("" if value is None else str(value)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourcedValueCommand:
    product_id: int
    target_kind: str  # name|short_description|description|attribute
    attribute_slug: str  # "" для текстов
    value: dict  # {"type": ..., "value": ...}
    source: str  # Source: web|marketplace
    confidence: float
    observed_value_hash: str
    observed_source: str
    allow_equal_override: bool = False


@dataclass(frozen=True)
class ApplyResult:
    status: str  # applied|skipped_locked|conflict|priority_blocked|invalid|missing_product|missing_attribute
    reason: str = ""


def _coerce(attr_type: str, envelope: dict):
    """Типизированный конверт → значение по типу атрибута. Ошибка → ValueError."""
    raw = envelope.get("value")
    if attr_type == AttributeType.INTEGER:
        return int(raw)
    if attr_type == AttributeType.DECIMAL:
        return Decimal(str(raw))
    if attr_type == AttributeType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        raise ValueError("not a bool")
    return str(raw)  # TEXT


def _current_attr_value(pav):
    for f in ("value_integer", "value_decimal", "value_boolean", "value_option"):
        v = getattr(pav, f)
        if v is not None:
            return v
    return pav.value_text or None


@transaction.atomic
def apply_sourced_value(cmd: SourcedValueCommand) -> ApplyResult:
    product = Product.objects.select_for_update().filter(pk=cmd.product_id).first()
    if product is None:
        return ApplyResult("missing_product")
    if product.content_locked:
        return ApplyResult("skipped_locked")

    if cmd.target_kind in _TEXT_TARGETS:
        current = getattr(product, cmd.target_kind) or ""
        if value_hash(current) != cmd.observed_value_hash:
            return ApplyResult("conflict", "baseline_changed")
        existing_source = (product.content_field_sources or {}).get(cmd.target_kind, "")
        if not can_overwrite(cmd.source, existing_source, allow_equal=cmd.allow_equal_override):
            return ApplyResult("priority_blocked")
        if cmd.value.get("type") != "text":
            return ApplyResult("invalid", "text target requires type=text")
        setattr(product, cmd.target_kind, str(cmd.value.get("value")))
        fields = dict(product.content_field_sources or {})
        fields[cmd.target_kind] = cmd.source
        product.content_field_sources = fields
        product.content_source = cmd.source  # last-applied (только текст)
        product.content_confidence = cmd.confidence
        product.save(
            update_fields=[
                cmd.target_kind,
                "content_field_sources",
                "content_source",
                "content_confidence",
            ]
        )
        return ApplyResult("applied")

    # attribute
    attr = Attribute.objects.filter(slug=cmd.attribute_slug).first()
    if attr is None:
        return ApplyResult("missing_attribute")
    pav = ProductAttributeValue.objects.filter(product=product, attribute=attr).first()
    current_source = pav.source if pav else ""
    current_hash = value_hash(_current_attr_value(pav) if pav else None)
    if current_hash != cmd.observed_value_hash:
        return ApplyResult("conflict", "baseline_changed")
    if not can_overwrite(cmd.source, current_source, allow_equal=cmd.allow_equal_override):
        return ApplyResult("priority_blocked")
    try:
        coerced = _coerce(attr.attribute_type, cmd.value)
    except (TypeError, ValueError, InvalidOperation):
        return ApplyResult("invalid", "type mismatch")
    pav = pav or ProductAttributeValue(product=product, attribute=attr)
    for f in ("value_text", "value_integer", "value_decimal", "value_boolean", "value_option"):
        setattr(pav, f, None)
    pav.value_text = ""
    if attr.attribute_type == AttributeType.INTEGER:
        pav.value_integer = coerced
    elif attr.attribute_type == AttributeType.DECIMAL:
        pav.value_decimal = coerced
    elif attr.attribute_type == AttributeType.BOOLEAN:
        pav.value_boolean = coerced
    else:
        pav.value_text = coerced
    pav.source = cmd.source
    pav.confidence = max(0, min(100, int(round(cmd.confidence * 100))))
    pav.save()
    rebuild_attrs_cache(product)
    return ApplyResult("applied")
