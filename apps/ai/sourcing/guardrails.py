# apps/ai/sourcing/guardrails.py
"""Валидация находок: выход источника — недоверенный ввод."""
from __future__ import annotations

from dataclasses import replace

from .ports import Finding

ALLOWED_TARGETS = {"name", "short_description", "description", "attribute"}
# Поля, которые источник НИКОГДА не может тронуть (цена/остаток/статус).
FORBIDDEN_ATTR_SLUGS = {"price", "stock_quantity", "available_quantity", "sync_1c_status"}
MAX_TEXT = 8000


def validate(finding: Finding) -> Finding | None:
    if finding.target_kind not in ALLOWED_TARGETS:
        return None
    if finding.target_kind == "attribute" and finding.attribute_slug in FORBIDDEN_ATTR_SLUGS:
        return None
    if finding.source_name == "web" and not finding.canonical_url:
        return None
    val = finding.value or {}
    if not isinstance(val, dict) or "type" not in val:
        return None
    if val.get("type") == "text" and len(str(val.get("value", ""))) > MAX_TEXT:
        return None
    conf = max(0.0, min(1.0, float(finding.confidence)))
    return replace(finding, confidence=conf)
