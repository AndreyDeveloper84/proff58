"""ПАРС-17 шаг 2 (read-only): сколько РЕАЛЬНЫХ совпадений теряет требование
брендового токена в имени товара.

Сверяет норм. артикулы каталога с manufacturer_sku живых карточек
resanta.ru / vihr.su (корпус ИЗО-07, 827 карточек со статусом 200).
В БД не пишет.
"""

import json
from collections import Counter, defaultdict

from apps.catalog import scraped_import as si
from apps.catalog.models import Product, ProductAttributeValue

TOKENS = list(si.BRAND_TOKEN_BY_SOURCE.values())
TOKEN_BY_SOURCE = si.BRAND_TOKEN_BY_SOURCE

# CARDS = {source: [ {sku, name}, ... ]}  — подставляется генератором
