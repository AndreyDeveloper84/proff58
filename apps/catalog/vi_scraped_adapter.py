"""VI-INT-01: адаптер артефактов Vseinstrumenti collector → контракт Phase-2 выгрузки.

Преобразует ``matches.json`` ВИ-коллектора (например, 25 MATCHED frozen pilot-30)
в формат выгрузки парсера Phase 2 — ``{"source": ..., "products": [...]}``, который
принимает существующая команда ``catalog_import_scraped``. Второго importer'а нет:
адаптер меняет только представление, запись остаётся за существующим pipeline.

Границы: детерминированный, без ORM/HTTP/Selenium/обращений к ВИ. Адаптируются
только ``MATCHED`` — SEARCH_KEY_MISS/IDENTITY_CONFLICT не имеют доказанной
identity и до importer'а не доходят. ``catalog_product_id`` (доказанная
collector'ом identity) сохраняется в карточке для последующей сверки с
результатом матчинга importer'а — сам importer его не читает.
"""
from __future__ import annotations

VI_SOURCE = "vseinstrumenti"

#: Поля карточки Phase-2, которые читает существующий importer.
_CARD_FIELDS = ("name", "brand", "manufacturer_sku", "source_url", "attributes")


def adapt_match_entry(entry: dict) -> tuple[dict, list[str]]:
    """Одна запись matches.json → карточка Phase-2 + список потерянных значений.

    ``attributes`` — словарь {подпись поля: сырое значение}. У ВИ встречаются
    ведущие пробелы в именах (« Размер max (T/E)») — снимаются. Дубликат имени
    внутри одной карточки (доказан один случай на pilot-30) не может существовать
    в контракте Phase-2: сохраняется ПЕРВОЕ значение, повторное уходит в
    ``dropped`` и обязано быть видно в отчётах, а не потеряно молча.
    """
    match = entry["match"]
    attrs: dict[str, str] = {}
    dropped: list[str] = []
    for c in entry.get("characteristics", []):
        name = (c["name"] or "").strip()
        if name in attrs:
            dropped.append(f"{name} = {c['value']!r} (дубликат имени, сохранено первое)")
            continue
        attrs[name] = c["value"]
    card = {
        "name": match["source_title"],
        "brand": match["source_brand"],
        "manufacturer_sku": match["source_article_raw"],
        "source_url": match["source_product_url"],
        "attributes": attrs,
        # Доказанная collector'ом identity — для сверки, importer не читает.
        "catalog_product_id": entry["product_id"],
    }
    return card, dropped


def adapt_matches(entries: list[dict]) -> tuple[list[dict], list[str]]:
    """matches.json → (карточки MATCHED в исходном порядке, dropped-заметки)."""
    cards: list[dict] = []
    dropped: list[str] = []
    for entry in entries:
        if entry["match"]["status"] != "MATCHED":
            continue
        card, entry_dropped = adapt_match_entry(entry)
        dropped.extend(f"{entry['product_id']}: {d}" for d in entry_dropped)
        cards.append(card)
    return cards, dropped


def build_export(cards: list[dict]) -> dict:
    """Карточки → Phase-2 выгрузка существующего importer'а."""
    return {"source": VI_SOURCE, "products": cards}
