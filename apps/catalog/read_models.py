"""Read-models каталога: денормализация EAV-характеристик в Product.attrs_cache.

`attrs_cache` — read-model `{slug_атрибута: значение}` для быстрых фасетов (#25)
и фильтров. Источник истины — `ProductAttributeValue`. Полная идемпотентная
пересборка из EAV (а не точечное обновление ключа).
"""

from __future__ import annotations

from .models import AttributeType, Product, ProductAttributeValue


def attr_value_to_json(pav: ProductAttributeValue):
    """JSON-safe значение характеристики по её типу.

    Decimal → float — намеренно и ТОЛЬКО для характеристик/фасетов (мощность, вес,
    диаметр и т.п.), не для денег: JSONField без encoder не умеет Decimal, а для
    числовых фильтров float достаточно.
    """
    t = pav.attribute.attribute_type
    if t == AttributeType.TEXT:
        return pav.value_text
    if t == AttributeType.INTEGER:
        return pav.value_integer
    if t == AttributeType.DECIMAL:
        return float(pav.value_decimal) if pav.value_decimal is not None else None
    if t == AttributeType.BOOLEAN:
        return pav.value_boolean
    if t in (AttributeType.SELECT, AttributeType.MULTISELECT):
        return pav.value_option.value if pav.value_option_id else None
    return None


def rebuild_attrs_cache(product: Product) -> dict:
    """Пересобрать Product.attrs_cache из EAV-значений. Идемпотентно."""
    cache: dict = {}
    for pav in product.attribute_values.select_related("attribute", "value_option"):
        value = attr_value_to_json(pav)
        # Пустые значения не кладём; boolean False — валидное значение, сохраняем.
        if value is not None and value != "":
            cache[pav.attribute.slug] = value
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])
    return cache
