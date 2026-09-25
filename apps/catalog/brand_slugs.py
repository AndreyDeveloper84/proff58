"""ЧПУ-slug брендов для PLP (полировка). Бренд — строка ``Product.brand`` (модели Brand нет),
поэтому slug-карта строится детерминированно из distinct видимых брендов; reuse
``translit.slugify_value``.

Известное ограничение: без модели Brand slug НЕ постоянный — стабилен лишь для ТЕКУЩЕГО
множества брендов (при добавлении/удалении suffix-slug может сдвинуться). Полноценные SEO-URL
требуют Brand-модели / persisted ``brand_slug`` (follow-up).

Две схемы slug — намеренно, и путать их нельзя:

* **фасет PLP** (``build_brand_slug_map``) — slug с суффиксами ``-2/-3`` при коллизии.
  Нужен, чтобы каждая строка фасета была отдельным токеном; от состава брендов зависит.
* **страница бренда** (``brand_page``, UX-07) — ТОЛЬКО base-slug, без суффиксов. Все
  написания с одним base-slug («Bosch»/«BOSCH», «Зубр»/«Zubr») — одна страница
  ``/brands/<slug>``. Поэтому публичная ссылка стабильна: появление или исчезновение
  другого бренда её не сдвигает. Это и есть решение по «стабильным ссылкам» до
  появления модели Brand.

Отдельный модуль (а не в facets/filters) — чтобы и ``facets.py``, и ``filters.py`` могли
импортировать резолв без циклической зависимости. ``visible_products`` импортируется лениво
(внутри функции), т.к. ``filters`` импортирует этот модуль.
"""

from __future__ import annotations

from django.core.cache import cache as cache_store
from django.db.models import Count, Q

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


# --- Страница бренда (UX-07) -------------------------------------------------------


def _build_brand_pages() -> dict[str, dict]:
    """``{base_slug: {"slug", "name", "spellings", "visible_total"}}`` по ВСЕМ товарам.

    По всем, а не только видимым: странице нужно отличать «такого бренда нет» (404) от
    «бренд известен, но товаров на витрине сейчас нет» (200 с нулём). ``name`` — самое
    частое написание среди видимых товаров (при равенстве — среди всех, затем по
    алфавиту), чтобы заголовок не зависел от порядка строк в БД.
    """
    from apps.catalog.models import Product, ProductStatus  # lazy: модуль грузится рано

    rows = (
        Product.objects.exclude(brand__isnull=True)
        .exclude(brand__exact="")
        .order_by()  # сбросить Meta.ordering, иначе name попадёт в GROUP BY
        .values("brand")
        .annotate(
            total=Count("id"),
            visible=Count("id", filter=Q(is_active=True, status=ProductStatus.PUBLISHED)),
        )
    )
    pages: dict[str, dict] = {}
    for row in rows:
        slug = slugify_value(row["brand"])
        if not slug:
            continue
        page = pages.setdefault(slug, {"slug": slug, "_variants": []})
        page["_variants"].append((row["brand"], row["visible"], row["total"]))
    for page in pages.values():
        variants = sorted(
            page.pop("_variants"), key=lambda v: (-v[1], -v[2], v[0].casefold(), v[0])
        )
        page["name"] = variants[0][0]
        page["spellings"] = sorted(v[0] for v in variants)
        page["visible_total"] = sum(v[1] for v in variants)
    return pages


def brand_pages() -> dict[str, dict]:
    """Карта страниц брендов в версионном кэше фасетов.

    Инвалидируется вместе с фасетами (любое сохранение товара поднимает версию), TTL тот
    же. Кэш выключен (dev/CI) → прямой расчёт: один GROUP BY по индексированному полю.
    """
    from apps.catalog.facets import _facets_cache_ttl, _facets_version  # lazy: facets → brand_slugs

    ttl = _facets_cache_ttl()
    if ttl <= 0:
        return _build_brand_pages()
    key = f"catalog:brand-pages:v{_facets_version()}"
    cached = cache_store.get(key)
    if cached is not None:
        return cached
    pages = _build_brand_pages()
    cache_store.set(key, pages, ttl)
    return pages


def brand_page(slug: str) -> dict | None:
    """Страница бренда по base-slug; ``None`` — такого бренда нет ни у одного товара."""
    return brand_pages().get((slug or "").strip().lower())
