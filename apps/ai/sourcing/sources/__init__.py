# apps/ai/sourcing/sources/__init__.py
"""Реестр источников. Включённые — по наличию ключей (Task 8)."""
from __future__ import annotations

from .dummy import DummySource


def get_sources() -> list:
    """Сейчас только dummy (тест). Реальные адаптеры подключаются в Task 8 по ключам.
    Включённый sourcing без реальных источников → вызывающий ставит configuration_error."""
    return [DummySource()]
