# apps/ai/sourcing/sources/__init__.py
"""Реестр источников. Включаются по наличию ключей; иначе список пуст → configuration_error."""
from __future__ import annotations

from django.conf import settings

from .dummy import DummySource
from .marketplace import MarketplaceSource
from .web_search import WebSearchSource


def get_sources(*, include_dummy: bool = True) -> list:
    out = []
    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        out.append(WebSearchSource())
    if getattr(settings, "YANDEX_MARKET_API_KEY", ""):
        out.append(MarketplaceSource())
    if not out and include_dummy and settings.DEBUG:  # dummy — только dev/тест
        out.append(DummySource())
    return out
