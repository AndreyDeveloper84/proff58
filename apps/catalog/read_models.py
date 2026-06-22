"""Read-models каталога: денормализация EAV-характеристик в Product.attrs_cache.

`attrs_cache` — read-model `{slug_атрибута: значение}` для быстрых фасетов (#25)
и фильтров. Источник истины — `ProductAttributeValue`. Полная идемпотентная
пересборка из EAV (а не точечное обновление ключа).
"""

from __future__ import annotations

from .models import AttributeType, Product, ProductAttributeValue


def typed_value_to_json(
    attribute_type: str,
    *,
    text=None,
    integer=None,
    decimal=None,
    boolean=None,
    option_value=None,
):
    """ЯДРО конвертации: JSON-safe значение по логическому типу характеристики.

    Единый источник правил сериализации для всех путей (обычный PAV и batch-обогащение):
    оба обязаны давать ИДЕНТИЧНЫЙ результат для одной и той же характеристики.

    Эталонные правила (исторически из ``attr_value_to_json``):
      * TEXT       → str (как есть),
      * INTEGER    → int (как есть),
      * DECIMAL    → float (намеренно для характеристик/фасетов, не для денег:
                     JSONField без encoder не умеет Decimal, для числовых фильтров
                     float достаточно),
      * BOOLEAN    → bool (False СОХРАНЯЕТСЯ, не выбрасывается),
      * SELECT/MULTISELECT → option_value (рус. ярлык варианта),
      * None        → None.

    Значение каждого типа передаётся отдельным kwarg; используется только то,
    что соответствует ``attribute_type``.
    """
    if attribute_type == AttributeType.TEXT:
        return text
    if attribute_type == AttributeType.INTEGER:
        return integer
    if attribute_type == AttributeType.DECIMAL:
        return float(decimal) if decimal is not None else None
    if attribute_type == AttributeType.BOOLEAN:
        return boolean
    if attribute_type in (AttributeType.SELECT, AttributeType.MULTISELECT):
        return option_value
    return None


def attr_value_to_json(pav: ProductAttributeValue):
    """JSON-safe значение характеристики по её типу (ЭТАЛОН, путь обычного PAV).

    Адаптер над :func:`typed_value_to_json`: достаёт тип из ``pav.attribute`` и
    соответствующие ``value_*``/опцию. Поведение не меняется.
    """
    option_value = pav.value_option.value if pav.value_option_id else None
    return typed_value_to_json(
        pav.attribute.attribute_type,
        text=pav.value_text,
        integer=pav.value_integer,
        decimal=pav.value_decimal,
        boolean=pav.value_boolean,
        option_value=option_value,
    )


def extracted_value_to_json(attribute, av, option=None):
    """JSON-safe значение для attrs_cache из извлечённого значения (путь enrich).

    Адаптер над тем же ЯДРОМ :func:`typed_value_to_json`, что и ``attr_value_to_json``,
    поэтому результат ТОЧНО совпадает с обычным PAV-путём для того же атрибута.

    КЛЮЧЕВОЕ: логический тип берём из РЕАЛЬНОГО ``attribute.attribute_type`` (а не из
    грубого ``av.kind``). Это снимает любое возможное расхождение «float vs int»: чем бы
    ни был тип атрибута, ядро применит к нему те же правила, что и для PAV. ``av`` —
    :class:`~apps.catalog.attribute_extract.AttrValue` (поля ``number``/``boolean``),
    ``option`` — выбранный :class:`AttributeOption` для select-характеристик.
    """
    return typed_value_to_json(
        attribute.attribute_type,
        # number-экстракт пишется и в value_integer, и в value_decimal как одно
        # Decimal-число; ядро возьмёт нужное поле по реальному типу атрибута.
        integer=int(av.number) if av.number is not None else None,
        decimal=av.number,
        boolean=av.boolean,
        option_value=option.value if option is not None else None,
        # TEXT enrich не извлекает; на случай TEXT-атрибута дадим пустую строку,
        # которую rebuild_attrs_cache отбрасывает как пустое значение.
        text="",
    )


def _cache_from_pavs(pavs) -> dict:
    """Собрать словарь attrs_cache из итерируемого набора PAV (единая логика сборки)."""
    cache: dict = {}
    for pav in pavs:
        value = attr_value_to_json(pav)
        # Пустые значения не кладём; boolean False — валидное значение, сохраняем.
        if value is not None and value != "":
            cache[pav.attribute.slug] = value
    return cache


def build_attrs_cache(product: Product) -> dict:
    """Собрать словарь attrs_cache из EAV-значений товара (БЕЗ сохранения).

    Итерируется по ``product.attribute_values.all()``: если вызывающий заранее сделал
    ``prefetch_related("attribute_values__attribute", "attribute_values__value_option")``
    (батч-команда), Django отдаст значения из prefetch-кэша — без N+1. Для одиночного
    пути без prefetch (сигналы) ``.all()`` выполнит один запрос на PAV, но тогда
    обращение к ``attribute``/``value_option`` даст доп. запросы — поэтому одиночный
    :func:`rebuild_attrs_cache` использует select_related-вариант, см. ниже.
    """
    return _cache_from_pavs(product.attribute_values.all())


def rebuild_attrs_cache(product: Product) -> dict:
    """Пересобрать Product.attrs_cache из EAV-значений и сохранить. Идемпотентно.

    Зовётся сигналами и тестами — поведение НЕ меняется. Чтобы одиночный путь не
    порождал N+1 (как и прежняя реализация), читаем PAV одним запросом с
    ``select_related("attribute", "value_option")``; сборка — общая с батчем.
    """
    cache = _cache_from_pavs(product.attribute_values.select_related("attribute", "value_option"))
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])
    return cache
