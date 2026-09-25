"""Оффлайн-проверка матчинга: наши товары (SELECT-выгрузка) vs URL источников из fixtures.

Сеть не трогает. Считает, сколько наших моделей находится в каталоге производителя
по нормализованной модели из названия.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(__file__).resolve().parent
FX = BASE / "fixtures"

TRANS = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
        "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch",
        "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)


def norm(s: str) -> str:
    """Ключ модели: транслит + только буквы/цифры."""
    return re.sub(r"[^a-z0-9]", "", s.lower().translate(TRANS))


BRANDS = {
    "вихрь": "ВИХРЬ",
    "ресанта": "РЕСАНТА",
    "интерскол": "ИНТЕРСКОЛ",
    "зубр": "ЗУБР",
}

# модель из названия: П-30-900К, П-24/700ЭР, ЗП-28-800 К, ПА-10/14,4Р …
MODEL_RE = re.compile(
    r"\b((?:ЗПМ|ЗПВ|ЗП|ПА|ПВ|П)[-\s]?\d+(?:[-/,.]\d+)*(?:\s?[А-ЯA-Z]{1,3})?(?:-[А-ЯA-Z]{1,3})?)",
    re.I,
)


def source_keys() -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {b: set() for b in BRANDS.values()}
    sm = {
        "РЕСАНТА": FX / "resanta.ru" / "sitemap-shop.xml.xml",
        "ВИХРЬ": FX / "vihr.su" / "sitemap-shop.xml.xml",
        "ИНТЕРСКОЛ": FX / "interskol.ru" / "sitemap.xml.xml",
    }
    for brand, path in sm.items():
        txt = path.read_text(encoding="utf-8", errors="replace")
        for u in re.findall(r"https?://[^<\s]+", txt):
            if "perforator" not in u:
                continue
            if "/news/" in u:
                continue
            slug = norm(u.rstrip("/").rsplit("/", 1)[-1])
            for junk in ("perforator", "resanta", "vihr", "vikhr", "interskol", "sdsplus",
                         "sdsmax", "professionalnyy", "trehrezhimnyy", "dvuhrezhimnyy",
                         "svibrozaschitoy", "santivibraciey", "santivibracionnoy",
                         "sbesschetochnymdvigatelemi", "akkumulyatornyy"):
                slug = slug.replace(junk, "")
            if slug:
                keys[brand].add(slug)
    for zf in FX.glob("zubr.ru/*.html"):
        zt = zf.read_text(encoding="utf-8", errors="replace")
        for href in set(re.findall(r'href="[^"]*/([a-z0-9-]+)/\?ID=', zt)):
            keys["ЗУБР"].add(norm(re.sub(r"-[a-z0-9]{4}$", "", href)))
    return keys


def main() -> None:
    src = source_keys()
    for b, s in src.items():
        print(f"{b}: {len(s)} моделей в каталоге источника (fixtures) -> {sorted(s)}")
    print()
    rows = [
        line.split("|")
        for line in (BASE / "our-perf-ru.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stat = {b: [0, 0] for b in BRANDS.values()}
    for pid, art, name in rows:
        brand = next((v for k, v in BRANDS.items() if k in name.lower()), "?")
        m = MODEL_RE.search(name.replace("Перф.", " ").replace("Перфоратор", " "))
        model = m.group(1).strip() if m else ""
        # у ЗУБРа модель надёжнее берётся из article, а не из названия
        if brand == "ЗУБР" and art:
            model = art
        key = norm(model)
        hit = ""
        if len(key) >= 5:
            for cand in sorted(src.get(brand, ()), key=len):
                if cand == key:
                    hit = cand
                    break
            if not hit:
                for cand in sorted(src.get(brand, ()), key=len):
                    if key in cand or cand in key:
                        hit = cand + " (частично)"
                        break
        stat[brand][1] += 1
        if hit:
            stat[brand][0] += 1
        print(f"{pid:>6} {brand:10} art={art:16} model={model:16} key={key:14} -> {hit or 'НЕТ'}")
    print("\nИТОГО по брендам (найдено/всего в нашей выборке):")
    for b, (ok, tot) in stat.items():
        print(f"  {b:10} {ok}/{tot}")


if __name__ == "__main__":
    main()
