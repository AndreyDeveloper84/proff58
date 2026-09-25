"""Разбор структуры карточки из fixtures — только stdlib, без сети.

    uv run python scratchpad/parser-mvp/analyze_card.py <fixture.html> [...]
"""

from __future__ import annotations

import json
import re
import sys
from html import unescape
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")


def text(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub(" ", s))).strip()


def jsonld(html: str) -> list:
    out = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I
    ):
        raw = m.group(1).strip()
        try:
            out.append(json.loads(raw))
        except Exception:
            out.append({"__parse_error__": raw[:400]})
    return out


def microdata(html: str) -> dict:
    """itemprop -> список значений (content=... или текст элемента)."""
    res: dict[str, list[str]] = {}
    for m in re.finditer(r"<(\w+)([^>]*\bitemprop=[\"']([^\"']+)[\"'][^>]*)>", html, re.I):
        tag, attrs, prop = m.group(1), m.group(2), m.group(3)
        val = None
        cm = re.search(r'\bcontent=["\']([^"\']*)["\']', attrs)
        if cm:
            val = cm.group(1)
        else:
            hm = re.search(r'\bhref=["\']([^"\']*)["\']', attrs)
            if hm and tag.lower() in ("a", "link"):
                val = hm.group(1)
            else:
                tail = html[m.end() : m.end() + 600]
                close = tail.find(f"</{tag}")
                val = text(tail[: close if close > -1 else 200])[:160]
        res.setdefault(prop, []).append(val or "")
    return res


def spec_tables(html: str) -> list[tuple[str, str]]:
    """Пары «параметр — значение» из таблиц и dl/li-списков."""
    pairs: list[tuple[str, str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        cells = [c for c in cells if c]
        if len(cells) == 2:
            pairs.append((cells[0], cells[1]))
    # webasyst-тема vihr/resanta: div.…features--item__name / …__value
    for m in re.finditer(
        r'class="[^"]*(?:features?|param|spec)[^"]*__name"[^>]*>(.*?)</div>\s*'
        r'<div[^>]*class="[^"]*(?:features?|param|spec)[^"]*__value"[^>]*>(.*?)</div>',
        html,
        re.S | re.I,
    ):
        k, v = text(m.group(1)), text(m.group(2))
        if k and v:
            pairs.append((k, v))
    # <div class="...feature..."><span>имя</span><span>значение</span>
    for blk in re.findall(
        r'<(?:li|div|p)[^>]*class="[^"]*(?:features?|param|characteristic|spec)[^"]*"[^>]*>(.*?)</(?:li|div|p)>',
        html,
        re.S | re.I,
    ):
        spans = [text(s) for s in re.findall(r"<span[^>]*>(.*?)</span>", blk, re.S | re.I)]
        spans = [s for s in spans if s]
        if len(spans) == 2:
            pairs.append((spans[0], spans[1]))
    seen, out = set(), []
    for k, v in pairs:
        if (k, v) not in seen and len(k) < 120 and len(v) < 200:
            seen.add((k, v))
            out.append((k, v))
    return out


def main(paths: list[str]) -> None:
    for p in paths:
        html = Path(p).read_text(encoding="utf-8", errors="replace")
        print("=" * 100)
        print(f"FILE {p}  ({len(html)} chars)")
        ld = jsonld(html)
        print(f"\n--- JSON-LD блоков: {len(ld)}")
        for b in ld:
            print(json.dumps(b, ensure_ascii=False)[:1500])
        md = microdata(html)
        print(f"\n--- microdata itemprop: {len(md)} уникальных")
        for k, v in sorted(md.items()):
            print(f"  {k:22} x{len(v):<3} {str(v[:2])[:180]}")
        sp = spec_tables(html)
        print(f"\n--- пары «параметр — значение»: {len(sp)}")
        for k, v in sp:
            print(f"  {k:45} | {v}")
        for pat, label in (
            (r"[Аа]ртикул[^<]{0,20}", "артикул"),
            (r"itemtype=[\"']([^\"']+)[\"']", "itemtype"),
        ):
            hits = re.findall(pat, html)
            print(f"\n--- {label}: {sorted(set(hits))[:12]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
