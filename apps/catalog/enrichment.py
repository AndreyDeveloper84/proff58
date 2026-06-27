# apps/catalog/enrichment.py
"""Применение AI-результата к каталогу — единственная точка записи enrich.

apps/ai сюда делегирует чтение и запись (граница ADR-0004: ai не трогает таблицы
каталога напрямую). Правила: content_locked неприкосновенен; карточные поля
пишутся только в пустоту (или при force); PAV source=llm — только в пробел или
поверх llm (низший приоритет провенанса); attrs_cache пересобирается.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import (Attribute, AttributeType, ContentSource, EnrichStatus, Product,
                     ProductAttributeValue, Source)
from .read_models import rebuild_attrs_cache

MODERATION_THRESHOLD = 0.7
LLM_CONFIDENCE_DEFAULT = 60
_VALUE_FIELDS = ["value_text", "value_integer", "value_decimal", "value_boolean",
                 "value_option"]


@dataclass
class AiAttr:
    slug: str
    value: object
    confidence: int = LLM_CONFIDENCE_DEFAULT


def get_enrichable_product(pk: int) -> Product | None:
    """Товар по pk для обогащения (в т.ч. неопубликованный)."""
    return Product.objects.filter(pk=pk).select_related("category").first()


def pending_for_enrichment(*, category_slug: str | None = None, limit: int = 100,
                           only_empty: bool = True) -> list[int]:
    """id товаров для батча: pending, не locked, приоритет available_quantity>0."""
    qs = Product.objects.filter(content_locked=False, enrich_status=EnrichStatus.PENDING)
    if only_empty:
        qs = qs.filter(description="")
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    return list(qs.order_by("-available_quantity", "id")
               .values_list("id", flat=True)[:limit])


def _set_typed_value(pav: ProductAttributeValue, attr: Attribute, value) -> bool:
    for f in _VALUE_FIELDS:
        setattr(pav, f, None)
    pav.value_text = ""
    try:
        if attr.attribute_type == AttributeType.INTEGER:
            pav.value_integer = int(value)
        elif attr.attribute_type == AttributeType.DECIMAL:
            pav.value_decimal = Decimal(str(value))
        elif attr.attribute_type == AttributeType.BOOLEAN:
            pav.value_boolean = bool(value)
        else:  # TEXT (SELECT/MULTISELECT из LLM в этой итерации не поддерживаем)
            pav.value_text = str(value)
    except (TypeError, ValueError, InvalidOperation):
        return False
    return True


def _apply_attributes(product: Product, attributes: list[AiAttr]) -> list[str]:
    updated: list[str] = []
    for ai_attr in attributes:
        attr = Attribute.objects.filter(slug=ai_attr.slug).first()
        if attr is None or attr.attribute_type in (AttributeType.SELECT,
                                                   AttributeType.MULTISELECT):
            continue
        existing = ProductAttributeValue.objects.filter(product=product,
                                                        attribute=attr).first()
        if existing is not None and existing.source != Source.LLM:
            continue  # llm — низший приоритет: не затираем manual/1c/regex/keyword
        pav = existing or ProductAttributeValue(product=product, attribute=attr)
        if not _set_typed_value(pav, attr, ai_attr.value):
            continue
        pav.source = Source.LLM
        pav.confidence = max(0, min(100, ai_attr.confidence))
        pav.save()
        updated.append(ai_attr.slug)
    return updated


@transaction.atomic
def apply_ai_enrichment(product: Product, *, name=None, short_description=None,
                        description=None, attributes: list[AiAttr] = (),
                        confidence: float | None = None, force: bool = False) -> dict:
    if product.content_locked and not force:
        return {"locked": True, "fields_updated": []}

    fields: list[str] = []
    if name and (force or not product.name):
        product.name = name
        fields.append("name")
    if short_description and (force or not product.short_description):
        product.short_description = short_description
        fields.append("short_description")
    if description and (force or not product.description):
        product.description = description
        fields.append("description")

    attr_updated = _apply_attributes(product, list(attributes))

    product.content_source = ContentSource.LLM
    product.content_confidence = confidence
    if confidence is not None and confidence < MODERATION_THRESHOLD:
        product.enrich_status = EnrichStatus.MODERATION
    else:
        product.enrich_status = EnrichStatus.DONE
    product.save(update_fields=["name", "short_description", "description",
                                "content_source", "content_confidence", "enrich_status"])
    if attr_updated:
        rebuild_attrs_cache(product)
    return {"locked": False, "fields_updated": fields + attr_updated,
            "status": product.enrich_status}
