"""Сборка локальных шрифтов витрины из исходников Google Fonts (DRF-2734).

Раньше шрифты подключались через ``next/font/google``: каждая сборка витрины
скачивала их с fonts.googleapis.com, и сбой сети ронял выкат. Теперь файлы лежат
в репозитории (``frontend/app/fonts``), а этот скрипт — способ получить их
заново: те же версии шрифтов, те же оси и тот же набор OpenType-функций, что
отдавал Google, но одним файлом на семейство.

Что нужно положить рядом (в текущий каталог запуска):
  Inter.ttf   — ofl/inter/Inter[opsz,wght].ttf из github.com/google/fonts
  Oswald.ttf  — ofl/oswald/Oswald[wght].ttf оттуда же

Запуск (нужны fonttools и brotli — они есть в образе proff58-web):
  python scripts/fonts/build_fonts.py

Результат: inter-var.woff2 и oswald-var.woff2 в текущем каталоге — их копируют в
``frontend/app/fonts``. Подробности и проверка — ``frontend/app/fonts/README.md``.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

COVERAGE = Path(__file__).with_name("coverage.json")

# Семейство → (исходник, оси, функции, результат).
#
# Оси как у Google: у Inter оптический размер зафиксирован на значении по
# умолчанию, у Oswald жирность ограничена диапазоном, который отдавался сайту.
#
# OpenType-функции — ровно те, что оставлял Google Fonts. Остальные (стилистические
# наборы, капитель, альтернативы) витрина не использует, а весят они треть файла.
# tnum нужен: цены и таблицы набраны табличными цифрами.
FAMILIES = {
    "inter": (
        "Inter.ttf",
        {"opsz": 14},
        ["calt", "ccmp", "dnom", "frac", "locl", "numr", "pnum", "tnum", "kern", "mark", "mkmk"],
        "inter-var.woff2",
    ),
    "oswald": (
        "Oswald.ttf",
        {"wght": (400, 700)},
        ["ccmp", "frac", "liga", "locl", "kern", "mark", "mkmk"],
        "oswald-var.woff2",
    ),
}


def parse_ranges(ranges: list[str]) -> set[int]:
    """``["U+0020-007E", "U+20BD"]`` → множество кодов символов."""
    codes: set[int] = set()
    for item in ranges:
        first, _, last = item.removeprefix("U+").partition("-")
        codes.update(range(int(first, 16), int(last or first, 16) + 1))
    return codes


def build(name: str) -> None:
    source, axes, features, target = FAMILIES[name]
    coverage = parse_ranges(json.loads(COVERAGE.read_text(encoding="utf-8"))[name])
    # recalcTimestamp=False: иначе в файл вписывается время сборки, и повторный
    # запуск даёт другие байты — сверить результат с лежащим в репозитории нельзя.
    # После фиксации осей шрифт сохраняем и читаем заново: subset работает с
    # таблицей вариаций лениво и на несохранённом результате падает.
    pinned = io.BytesIO()
    instancer.instantiateVariableFont(TTFont(source, recalcTimestamp=False), axes).save(pinned)
    pinned.seek(0)
    font = TTFont(pinned, recalcTimestamp=False)

    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = features
    options.hinting = False
    options.glyph_names = False
    options.notdef_outline = True

    cmap = font.getBestCmap()
    unicodes = sorted(code for code in coverage if code in cmap)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(target)
    size = os.path.getsize(target)
    print(f"{target}: {size} байт, символов {len(unicodes)}, глифов {len(font.getGlyphOrder())}")


if __name__ == "__main__":
    for family in FAMILIES:
        build(family)
