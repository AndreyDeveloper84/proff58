"""VI-INT-01: контрактные тесты адаптера ВИ на fixture 25 MATCHED frozen pilot-30.

Fixture — реальный matches.json завершённого pilot-30 (tests/fixtures/
vi-pilot30-matched-25.json). Прогон без ВИ, без браузера, без БД.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.catalog.vi_scraped_adapter import (
    VI_SOURCE,
    adapt_match_entry,
    adapt_matches,
    build_export,
)

FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "vi-pilot30-matched-25.json"
EXPECTED_PRODUCT_IDS = [
    36918,
    2092,
    37265,
    41489,
    42047,
    43419,
    10812,
    41821,
    15728,
    519,
    22671,
    26841,
    6213,
    44122,
    34270,
    34538,
    6616,
    36131,
    36337,
    32407,
    44891,
    35079,
    43749,
    6794,
    7057,
]


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cards(entries):
    cards, _dropped = adapt_matches(entries)
    return cards


def test_fixture_is_25_matched(entries):
    assert len(entries) == 25
    assert all(e["match"]["status"] == "MATCHED" for e in entries)


def test_all_25_artifacts_accepted(cards):
    assert len(cards) == 25


def test_proven_identity_preserved(cards):
    """Доказанная collector'ом identity не теряется ни на одной карточке."""
    ids = [c["catalog_product_id"] for c in cards]
    assert sorted(ids) == sorted(EXPECTED_PRODUCT_IDS)
    assert len(set(ids)) == 25, "дублей product_id быть не должно"


def test_card_contract_fields(cards):
    for c in cards:
        assert c["name"], "name обязателен для лестницы модели"
        assert c["manufacturer_sku"], "sku обязателен для ступени SKU"
        assert c["source_url"].startswith("https://www.vseinstrumenti.ru/")
        assert isinstance(c["attributes"], dict)
        assert all(isinstance(k, str) and k == k.strip() for k in c["attributes"])


def test_characteristics_preserved_except_declared_duplicate(entries, cards):
    """250 характеристик = 249 в атрибутах + 1 объявленный dropped-дубликат."""
    total = sum(len(e.get("characteristics", [])) for e in entries)
    adapted = sum(len(c["attributes"]) for c in cards)
    _, dropped = adapt_matches(entries)
    assert total == 250
    assert adapted == 249
    assert len(dropped) == 1
    assert "35079" in dropped[0]


def test_duplicate_name_keeps_first():
    entry = {
        "product_id": 1,
        "match": {
            "status": "MATCHED",
            "source_title": "X",
            "source_brand": "B",
            "source_article_raw": "A-1",
            "source_product_url": "https://www.vseinstrumenti.ru/product/x-1/",
        },
        "characteristics": [
            {"name": "Материал", "value": "сталь", "unit": None},
            {"name": " Материал ", "value": "чугун", "unit": None},
        ],
    }
    card, dropped = adapt_match_entry(entry)
    assert card["attributes"] == {"Материал": "сталь"}
    assert len(dropped) == 1


def test_non_matched_never_adapted(entries):
    bad = [dict(e, match={**e["match"], "status": "IDENTITY_CONFLICT"}) for e in entries[:1]]
    cards, _ = adapt_matches(bad)
    assert cards == []


def test_deterministic(entries):
    first = build_export(adapt_matches(entries)[0])
    second = build_export(adapt_matches(entries)[0])
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )


def test_export_contract(cards):
    export = build_export(cards)
    assert export["source"] == VI_SOURCE
    assert export["products"] == cards
