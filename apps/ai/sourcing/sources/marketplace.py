# apps/ai/sourcing/sources/marketplace.py
"""Источник по API маркетплейса (Яндекс.Маркет и пр.). Живые вызовы — за ключом."""
from __future__ import annotations

from ..ports import SourceQuery, SourceReply


class MarketplaceSource:
    name = "marketplace"

    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply:
        raise NotImplementedError(
            "MarketplaceSource — каркас; живой вызов появится в отдельном PR при YANDEX_MARKET_API_KEY"
        )
