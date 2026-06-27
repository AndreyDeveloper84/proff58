# apps/ai/ports.py
"""Порт-абстракция вызова модели (ARCHITECTURE-AI §5).

Сервисы знают только порт. Конкретный провайдер выбирается ``get_provider()``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


@dataclass(frozen=True)
class ModelCall:
    system: str
    user: str
    max_tokens: int = 1024


@dataclass(frozen=True)
class ModelReply:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    provider: str = ""


class ModelPort(Protocol):
    def complete(self, call: ModelCall) -> ModelReply: ...


def get_provider() -> ModelPort:
    """claude при наличии ключа, иначе детерминированный dummy."""
    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        from .providers.claude import ClaudeProvider

        return ClaudeProvider()
    from .providers.dummy import DummyProvider

    return DummyProvider()
