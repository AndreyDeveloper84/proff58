"""Разведка карточек производителей — Трек 2 · Phase 1.

READ-ONLY: скачивает страницу один раз, кладёт в fixtures, повторно НЕ ходит.
Режим доступа: 1 запрос в 3 секунды на домен, последовательно, честный User-Agent.
Фотографии не скачиваются — только HTML.

Использование:
    uv run python scratchpad/parser-mvp/inspect_page.py fetch <url> [<url> ...]
    uv run python scratchpad/parser-mvp/inspect_page.py robots <domain> [...]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = Path(__file__).resolve().parent
FIXTURES = BASE / "fixtures"
LOG = BASE / "fetch-log.jsonl"

UA = (
    "proff58-catalog-recon/0.1 (+https://proff58.ru; contact: sktajem95@gmail.com) "
    "one-off structure recon, 1 req/3s, no images"
)
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml"}

DELAY_SEC = 3.0
_last_hit: dict[str, float] = {}


def _fixture_path(url: str) -> Path:
    p = urlparse(url)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", (p.path + ("?" + p.query if p.query else ""))).strip("_")
    if not slug:
        slug = "index"
    if len(slug) > 80:
        slug = slug[:70] + "_" + hashlib.md5(slug.encode()).hexdigest()[:8]
    ext = ".xml" if slug.endswith(".xml") or "sitemap" in slug else ".html"
    if slug.endswith(".txt"):
        ext = ""
    return FIXTURES / p.netloc / (slug + ext)


def _throttle(host: str) -> float:
    now = time.monotonic()
    prev = _last_hit.get(host)
    waited = 0.0
    if prev is not None:
        need = DELAY_SEC - (now - prev)
        if need > 0:
            time.sleep(need)
            waited = need
    _last_hit[host] = time.monotonic()
    return waited


def fetch(url: str, force: bool = False) -> Path | None:
    dest = _fixture_path(url)
    if dest.exists() and not force:
        print(f"[cache] {url} -> {dest.relative_to(BASE)} ({dest.stat().st_size} B)")
        return dest
    host = urlparse(url).netloc
    waited = _throttle(host)
    t0 = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        _log({"url": url, "error": repr(exc), "waited_s": round(waited, 2)})
        print(f"[ERR ] {url}: {exc}")
        return None
    dt = time.time() - t0
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": url,
        "final_url": r.url,
        "status": r.status_code,
        "bytes": len(r.content),
        "encoding": r.encoding,
        "elapsed_s": round(dt, 2),
        "throttle_wait_s": round(waited, 2),
        "ctype": r.headers.get("Content-Type", ""),
    }
    _log(rec)
    print(f"[{r.status_code}] {url} {len(r.content)}B wait={waited:.1f}s")
    if r.status_code in (401, 403, 429):
        print("!!! СТОП: источник отказал. Обходы не подбираем, докладываем.")
        return None
    if r.status_code != 200:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def _log(rec: dict) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    args = sys.argv[2:]
    if mode == "robots":
        urls = [f"https://{d}/robots.txt" for d in args]
    else:
        urls = args
    for u in urls:
        fetch(u)
