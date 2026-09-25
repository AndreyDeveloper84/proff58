# apps/ai/providers/claude.py
"""Каркас реального провайдера. Живые вызовы — следующая итерация.

Активируется ``get_provider()`` при непустом ``settings.ANTHROPIC_API_KEY``.
Пока метод явно не реализован — осознанная заглушка под будущий PR.
"""
from __future__ import annotations

from ..ports import ModelCall, ModelReply


class ClaudeProvider:
    name = "claude"
    model = "claude-sonnet-4-6"

    def complete(self, call: ModelCall) -> ModelReply:
        raise NotImplementedError(
            "ClaudeProvider — каркас; живые вызовы появятся в отдельной итерации"
        )
