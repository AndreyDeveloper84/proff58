# apps/ai/sourcing/safety.py
"""Безопасность web-источника: allowlist по нормализованному hostname (не endswith)."""
from __future__ import annotations

from urllib.parse import urlparse


def _host(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https":
        return ""
    return (p.hostname or "").lower().rstrip(".")


def host_allowed(url: str, allowlist) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in allowlist)
