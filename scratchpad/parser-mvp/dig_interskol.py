"""Разбор RSC-payload карточки interskol.ru (Next.js) — только из fixtures."""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = Path(sys.argv[1])
h = p.read_text(encoding="utf-8", errors="replace")

print("TITLE:", re.search(r"<title>(.*?)</title>", h, re.S).group(1).strip())

# RSC payload экранирован дважды: \\" -> "
u = h.replace('\\\\"', '"').replace('\\"', '"')

pairs = re.findall(
    r'"property":\{[^{}]*"name":"(.*?)","slug":"(.*?)"\},"value":\{[^{}]*"value":"(.*?)","slug":"(.*?)"\}',
    u,
)
print(f"\n--- PropertyValue из RSC-payload: {len(pairs)}")
seen = set()
for n, s, v, vs in pairs:
    if (n, v) in seen:
        continue
    seen.add((n, v))
    print(f"  {n:34} [{s:24}] = {v}")

for kw in ("article", "sku", "vendorCode", "code", "model"):
    hits = sorted(set(re.findall(r'"' + kw + r'":"?([^",]{1,40})', u, re.I)))[:10]
    print(f"\n## {kw}: {hits}")

print("\n## Артикул в HTML:", re.findall(r"Артикул:\s*(?:<!--\s*-->)?([^<]{1,30})", h)[:5])
print("## h1:", [re.sub(r"\s+", " ", x)[:120] for x in re.findall(r"<h1[^>]*>(.*?)</h1>", h, re.S)][:3])
