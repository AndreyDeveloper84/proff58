# apps/ai/sourcing/sources/web_search.py
"""Web-поиск через Claude web_search / search API. Живые вызовы — за ключом.

Реализация сети — отдельный PR при наличии ANTHROPIC_API_KEY; здесь контракт и
безопасность (allowlist/https). Без сети метод явно не реализован (как claude.py в enrich)."""
from __future__ import annotations

from django.conf import settings

from ..ports import SourceQuery, SourceReply
from ..safety import host_allowed


class WebSearchSource:
    name = "web"

    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply:
        raise NotImplementedError(
            "WebSearchSource — каркас; живой вызов появится в отдельном PR при ANTHROPIC_API_KEY"
        )

    @staticmethod
    def _accept(url: str) -> bool:
        return host_allowed(url, settings.SOURCING_ALLOWLIST)
