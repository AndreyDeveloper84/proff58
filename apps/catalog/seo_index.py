"""Политика индексации товаров витрины (PF-SH-RELEASE-01).

Индексируются только товары из замороженного allowlist — INDEXABLE_CANDIDATE
release-gate manifest (``data/seo/indexable_products.json``, ссылка на manifest и его
sha256 внутри). Остальной каталог отдаётся витрине с ``seo_indexable=false`` (noindex)
и не попадает в sitemap. Allowlist — данные, а не флаг в БД: выпуск не меняет товары,
откат — правка одного файла.

Нет файла или он битый — не индексируется ничего (fail-closed).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def indexable_product_ids() -> frozenset[int]:
    path = Path(settings.SEO_INDEXABLE_PRODUCTS_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return frozenset(int(pid) for pid in data["product_ids"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("SEO allowlist недоступен (%s): индексация закрыта для всех товаров", exc)
        return frozenset()


def is_indexable(product) -> bool:
    """Товар открыт для индексации: в allowlist и виден на витрине."""
    return product.id in indexable_product_ids() and product.is_visible
