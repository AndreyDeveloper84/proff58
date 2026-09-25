# apps/ai/sourcing/sources/dummy.py
"""Детерминированный источник для тестов. Без сети."""
from __future__ import annotations

from decimal import Decimal

from ..ports import Finding, SourceQuery, SourceReply


class DummySource:
    name = "dummy"

    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply:
        url = f"https://example.test/{query.article or 'item'}"
        findings = [
            Finding(
                target_kind="description",
                attribute_slug="",
                value={"type": "text", "value": f"{query.name} — описание из источника."},
                canonical_url=url,
                confidence=0.8,
                source_name="web",
            )
        ]
        return SourceReply(
            findings=findings,
            provider=self.name,
            tokens_in=5,
            tokens_out=20,
            cost=Decimal("0"),
            http_status=200,
            raw_excerpt="dummy",
        )
