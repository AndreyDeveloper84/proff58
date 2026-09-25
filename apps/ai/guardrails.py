# apps/ai/guardrails.py
"""Валидация выхода LLM (ARCHITECTURE-AI §7). Выход — недоверенный ввод.

``parse_enrich_output`` возвращает ``None`` на любой невалидный выход — вызывающий
деградирует (берёт то, что дал детерминированный слой), а не падает 500.
Защищённые поля (цена/остаток/заказ) физически отсутствуют в схеме.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
_REQUIRED = {"name", "short_description", "description", "attributes", "confidence"}


@dataclass(frozen=True)
class EnrichedAttr:
    slug: str
    value: object
    confidence: int = 60


@dataclass(frozen=True)
class EnrichResult:
    name: str | None
    short_description: str | None
    description: str | None
    attributes: list[EnrichedAttr]
    confidence: float
    source: str  # "llm" | "fallback"


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse_enrich_output(text: str) -> EnrichResult | None:
    data = _extract_json(text)
    if data is None or not _REQUIRED <= data.keys():
        return None
    try:
        conf = float(data["confidence"])
    except (TypeError, ValueError):
        return None
    attrs: list[EnrichedAttr] = []
    for raw in data.get("attributes") or []:
        if not isinstance(raw, dict) or "slug" not in raw or "value" not in raw:
            continue
        try:
            c = int(raw.get("confidence", 60))
        except (TypeError, ValueError):
            c = 60
        attrs.append(
            EnrichedAttr(slug=str(raw["slug"]), value=raw["value"], confidence=max(0, min(100, c)))
        )
    return EnrichResult(
        name=(str(data["name"]).strip() or None) if data["name"] else None,
        short_description=(
            (str(data["short_description"]).strip() or None) if data["short_description"] else None
        ),
        description=(str(data["description"]).strip() or None) if data["description"] else None,
        attributes=attrs,
        confidence=max(0.0, min(1.0, conf)),
        source="llm",
    )
