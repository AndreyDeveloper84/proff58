"""Семантическая классификация по словарю + транслит slug (общий модуль).

Используется командами `catalog_semantic_classify` (отчёт по дампу) и
`catalog_build_section` (создание узлов + расселение по БД). Один источник правил
и одна логика матчинга — без дублирования.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ё": "e",
}


def translit_slug(name: str) -> str:
    """Кириллица → латинский slug (для v2-узлов; save() иначе делает кириллицу)."""
    s = "".join(_TRANSLIT.get(ch, ch) for ch in (name or "").lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def load_rules(path: str = "data/product_type_rules.json"):
    """Вернуть (doc, compiled). compiled — список (subcat, subtype, conf, kw, exclude)."""
    doc = json.loads((Path(settings.BASE_DIR) / path).read_text(encoding="utf-8"))
    compiled = []
    for r in doc.get("rules", []):
        compiled.append(
            (
                r["subcat"],
                r.get("subtype"),
                r.get("confidence", "medium"),
                [re.compile(k) for k in r.get("keywords", [])],
                [re.compile(k) for k in r.get("exclude", [])],
            )
        )
    return doc, compiled


def _norm(s: str) -> str:
    return " " + re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")) + " "


def classify(name: str, compiled):
    """Первое сработавшее правило (с учётом exclude) → (subcat, subtype, conf, kw) или None."""
    nm = _norm(name)
    for subcat, subtype, conf, pats, expats in compiled:
        kw = next((p.pattern for p in pats if p.search(nm)), None)
        if kw is not None and not any(e.search(nm) for e in expats):
            return subcat, subtype, conf, kw
    return None
