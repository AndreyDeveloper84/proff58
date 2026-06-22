"""ЧПУ-slug брендов для PLP (полировка). Бренд — строка ``Product.brand`` (модели Brand нет),
поэтому slug-карта строится детерминированно из distinct видимых брендов; reuse
``translit.slugify_value``.

Известное ограничение: без модели Brand slug НЕ постоянный — стабилен лишь для ТЕКУЩЕГО
множества брендов (при добавлении/удалении suffix-slug может сдвинуться). Полноценные SEO-URL
требуют Brand-модели / persisted ``brand_slug`` (follow-up).

Отдельный модуль (а не в facets/filters) — чтобы и ``facets.py``, и ``filters.py`` могли
импортировать резолв без циклической зависимости. ``visible_products`` импортируется лениво
(внутри функции), т.к. ``filters`` импортирует этот модуль.
"""

from __future__ import annotations

from apps.catalog.translit import slugify_value


def _distinct_brands() -> list[str]:
    """Видимые непустые бренды, детерминированно отсортированные (casefold)."""
    from apps.catalog.filters import visible_products  # lazy: разрыв цикла filters↔brand_slugs

    brands = list(
        visible_products()
        .exclude(brand__isnull=True)
        .exclude(brand__exact="")
        .order_by(
            "brand"
        )  # сбросить Meta ordering=["name"], иначе name попадёт в SELECT и сломает distinct
        .values_list("brand", flat=True)
        .distinct()
    )
    brands.sort(key=str.casefold)
    return brands


def build_brand_slug_map() -> tuple[dict[str, str], dict[str, str]]:
    """``({slug: brand}, {brand: slug})`` по всем видимым брендам.

    Детерминированно: бренды отсортированы; коллизия base-slug → суффикс ``-2/-3``
    (а не «первый победил»). Один запрос distinct брендов.
    """
    slug_to_brand: dict[str, str] = {}
    brand_to_slug: dict[str, str] = {}
    used: set[str] = set()
    for brand in _distinct_brands():
        base = slugify_value(brand) or "brand"
        slug = base
        i = 2
        while slug in used:
            slug = f"{base}-{i}"
            i += 1
        used.add(slug)
        slug_to_brand[slug] = brand
        brand_to_slug[brand] = slug
    return slug_to_brand, brand_to_slug


def resolve_brand_tokens(tokens) -> list[str]:
    """slug|raw бренд → канонический ``Product.brand`` (dual-accept, дедуп с порядком).

    Токен, совпавший со slug → бренд из карты; иначе токен как есть (legacy сырой бренд
    или неизвестный — фильтр по нему просто ничего не найдёт).
    """
    slug_to_brand, _ = build_brand_slug_map()
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        brand = slug_to_brand.get(tok, tok)
        if brand not in seen:
            seen.add(brand)
            out.append(brand)
    return out
