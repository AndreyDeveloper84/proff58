# apps/ai/providers/dummy.py
"""Детерминированный провайдер: валидный enrich-JSON из original_name.

Без сети и без LLM. Используется сейчас и в тестах. Формирует короткое имя
(первые слова до токена с цифрой) и шаблонные описания.
"""
from __future__ import annotations

import json
import re

from ..ports import ModelCall, ModelReply

_NUM = re.compile(r"\d")


def _short_name(raw: str) -> str:
    words = []
    for w in raw.replace(";", " ").split():
        if _NUM.search(w) and len(words) >= 2:
            break
        words.append(w)
        if len(words) >= 4:
            break
    return " ".join(words) or raw[:64]


class DummyProvider:
    name = "dummy"
    model = "dummy-1"

    def complete(self, call: ModelCall) -> ModelReply:
        raw = call.user.strip()
        name = _short_name(raw)
        payload = {
            "name": name,
            "short_description": f"{name} — инструмент для профессионального применения.",
            "description": (
                f"{name}. Описание сгенерировано детерминированным провайдером "
                f"на основе данных из учётной системы. Применение, особенности и "
                f"назначение уточняются при наполнении карточки."
            ),
            "attributes": [],
            "confidence": 0.5,
        }
        text = json.dumps(payload, ensure_ascii=False)
        return ModelReply(
            text=text,
            tokens_in=len(raw.split()),
            tokens_out=len(text.split()),
            model=self.model,
            provider=self.name,
        )
