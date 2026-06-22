"""Создание и обновление Product из данных 1С.

Знает только про домен каталога (Product, категоризация, цена, остаток).
НЕ знает про staging, SyncLog, source_file, ImportResult и API — это слой
оркестрации (`use_cases.py`).

Главное правило: повторное обновление НЕ трогает ручной контент сайта
(категорию, витринное `name`, описание, SEO, фото, slug).
"""

from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify

from apps.catalog.categorization import ProductHint, categorize
from apps.catalog.models import Category, CategoryMappingRule, Product, ProductStatus
from apps.core.events import EventSource, product_created, product_updated

from . import pricing, stock
from .normalizers import Item

_SLUG_MAX = 512  # Product.slug.max_length
_SLUG_SUFFIX_RESERVED = 60  # запас под детерминированный «-{code_1c}»

# Бизнес-поля для определения «было ли реальное изменение» при обновлении.
# Денормализованные служебные timestamp'ы (*_updated_at) намеренно исключены —
# они меняются каждый раз и не несут смысла для подписчиков.
_TRACKED_FIELDS = [
    "price",
    "old_price",
    "currency",
    "stock_quantity",
    "reserved_quantity",
    "available_quantity",
    "stock_status",
    "original_name",
    "brand",
    "barcode",
    "unit",
    "is_active_1c",
    "source_group",
]


def _snapshot(product: Product) -> dict:
    return {f: getattr(product, f) for f in _TRACKED_FIELDS}


def create_product(
    item: Item, *, rules: list[CategoryMappingRule] | None = None
) -> tuple[Product, bool]:
    """Создать товар из строки 1С. Вернуть (product, categorized?).

    ``rules`` — предзагруженные правила категоризации (пакетный импорт), чтобы не читать
    `CategoryMappingRule` на каждую строку; ``None`` — categorize прочитает сам.
    """
    category, rule = categorize(
        ProductHint(
            name=item.name,
            article=item.article,
            brand=item.brand,
            source_group=item.source_group,
        ),
        rules=rules,
    )
    product = Product(
        code_1c=item.code_1c or None,
        article=item.article,
        barcode=item.barcode,
        original_name=item.name,
        name=item.name,  # витринное имя при создании = имя из 1С; далее правится вручную
        brand=item.brand,
        source_group=item.source_group,
        unit=item.unit,
        is_active_1c=item.is_active,
        category=category,
        matched_rule=rule,
        status=ProductStatus.DRAFT if category else ProductStatus.NEEDS_REVIEW,
    )
    product.save()  # нужен pk для записей цены/остатка
    pricing.set_current_price(product, item)
    stock.set_current_stock(product, item)
    product.save()
    transaction.on_commit(
        lambda pid=product.pk: product_created.send(
            sender=Product, product_id=pid, source=EventSource.ONE_C
        )
    )
    return product, category is not None


def update_existing(product: Product, item: Item, *, allow_basic_fields: bool = True) -> None:
    """Обновить существующий товар, не затрагивая ручной контент сайта."""
    before = _snapshot(product)

    pricing.set_current_price(product, item)
    stock.set_current_stock(product, item)

    if allow_basic_fields:
        if item.name:
            product.original_name = item.name  # витринное name НЕ трогаем
        if item.brand and not product.brand:
            product.brand = item.brand
        if item.barcode:
            product.barcode = item.barcode
        if item.unit:
            product.unit = item.unit
        if item.is_active is not None:
            product.is_active_1c = item.is_active
        if item.source_group:
            product.source_group = item.source_group

    # Категория, name(витрина), description, SEO, фото, slug — НЕ трогаем.
    product.save()

    changed_fields = [f for f in _TRACKED_FIELDS if before[f] != getattr(product, f)]
    if changed_fields:
        transaction.on_commit(
            lambda pid=product.pk, c=changed_fields: product_updated.send(
                sender=Product, product_id=pid, source=EventSource.ONE_C, changed_fields=c
            )
        )


# --- Пакетная сборка (#125B): мутации в памяти, без save/price/stock/событий ---


def slug_base(item: Item) -> str:
    """База slug из имени/идентификаторов (как `Product._build_unique_slug`, но из Item)."""
    base = ""
    for value in (item.name, item.article, item.code_1c, "tovar"):
        base = slugify(value or "", allow_unicode=True)
        if base:
            break
    return base[: _SLUG_MAX - _SLUG_SUFFIX_RESERVED] or "tovar"


def build_slug_for_import(item: Item, taken: set[str]) -> str:
    """Детерминированный уникальный slug для нового товара 1С — без N+1/гонки.

    База занята → `f"{base}-{code_1c}"` (code_1c уникален → стабильно и идемпотентно);
    нет code_1c → `-{article}`; в самом крайнем случае — числовой суффикс. ``taken``
    seed'ится одним запросом существующих slug-баз и пополняется внутри батча.
    """
    base = slug_base(item)
    slug = base
    if slug in taken:
        suffix = item.code_1c or item.article or ""
        slug = f"{base}-{slugify(suffix, allow_unicode=True)}" if suffix else base
        n = 2
        while slug in taken:
            slug = f"{base}-{n}"
            n += 1
    taken.add(slug)
    return slug


def build_new_product(
    item: Item, *, category: Category | None, rule: CategoryMappingRule | None, slug: str
) -> Product:
    """Собрать НЕсохранённый Product из строки 1С (slug предзадан, без save/price/stock)."""
    return Product(
        code_1c=item.code_1c or None,
        article=item.article,
        barcode=item.barcode,
        original_name=item.name,
        name=item.name,
        brand=item.brand,
        source_group=item.source_group,
        unit=item.unit,
        is_active_1c=item.is_active,
        category=category,
        matched_rule=rule,
        status=ProductStatus.DRAFT if category else ProductStatus.NEEDS_REVIEW,
        slug=slug,
    )


def apply_basic_fields(product: Product, item: Item, *, allow_basic_fields: bool = True) -> None:
    """Промутировать базовые поля из 1С (как `update_existing`, но без save/price/stock).

    Ручной контент (name-витрина, category, SEO, slug) НЕ трогаем.
    """
    if not allow_basic_fields:
        return
    if item.name:
        product.original_name = item.name
    if item.brand and not product.brand:
        product.brand = item.brand
    if item.barcode:
        product.barcode = item.barcode
    if item.unit:
        product.unit = item.unit
    if item.is_active is not None:
        product.is_active_1c = item.is_active
    if item.source_group:
        product.source_group = item.source_group


def snapshot(product: Product) -> dict:
    """Снимок отслеживаемых полей (для вычисления changed_fields в bulk)."""
    return _snapshot(product)
