# apps/ai/sourcing/ports.py
"""Порт внешнего источника контента. Сервисы знают только порт."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class SourceQuery:
    article: str
    name: str
    brand: str
    category: str
    needed_targets: list


@dataclass(frozen=True)
class Finding:
    target_kind: str
    attribute_slug: str
    value: dict
    canonical_url: str
    confidence: float
    source_name: str


@dataclass(frozen=True)
class SourceReply:
    findings: list  # list[Finding]
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    http_status: int | None = None
    raw_excerpt: str = ""


class ContentSourcePort(Protocol):
    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply: ...
