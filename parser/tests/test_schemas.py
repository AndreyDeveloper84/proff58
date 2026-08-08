"""Тесты pydantic-схем выгрузки парсера (parser.schemas)."""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from parser.schemas import ErrorRecord, ErrorsExport, Export, ProductCard

VALID_URL = "https://resanta.ru/perforator-p-30-900k-resanta/"
CATEGORY_URL = "https://resanta.ru/category/instrument-resanta/perforatory-resanta/"


def make_card(**overrides):
    data = {"source_url": VALID_URL, "name": "Перфоратор П-30/900К"}
    data.update(overrides)
    return ProductCard(**data)


def test_valid_card_passes():
    card = make_card(brand="Ресанта", attributes={"Мощность, Вт": "900"})
    assert card.source_url == VALID_URL
    assert card.name == "Перфоратор П-30/900К"
    assert card.brand == "Ресанта"
    assert card.manufacturer_sku is None
    assert card.summary_raw is None


def test_name_whitespace_collapsed():
    card = make_card(name="  Перфоратор\n  П-30  ")
    assert card.name == "Перфоратор П-30"


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        make_card(name="   \n  ")


@pytest.mark.parametrize(
    "bad_url",
    ["ftp://example.com/x", "example.com/x", "http://", "/relative/path", ""],
)
def test_bad_source_url_rejected(bad_url):
    with pytest.raises(ValidationError):
        make_card(source_url=bad_url)


def test_raw_attribute_value_kept_as_is():
    card = make_card(attributes={"Напряжение питающей сети, В": "220-230В, ~50 Гц"})
    assert card.attributes["Напряжение питающей сети, В"] == "220-230В, ~50 Гц"


def test_attribute_whitespace_cleaned():
    card = make_card(attributes={"  Мощность,\n Вт ": " 900 "})
    assert card.attributes == {"Мощность, Вт": "900"}


def test_empty_attribute_value_rejected():
    with pytest.raises(ValidationError):
        make_card(attributes={"Мощность, Вт": "  "})


def test_empty_attribute_key_rejected():
    with pytest.raises(ValidationError):
        make_card(attributes={"  ": "900"})


def test_optional_text_empty_becomes_none():
    card = make_card(brand="   ", description=None)
    assert card.brand is None
    assert card.description is None


def make_export(**overrides):
    data = {
        "source": "resanta.ru",
        "category": {"name": "Перфораторы", "source_url": CATEGORY_URL},
        "products": [make_card()],
    }
    data.update(overrides)
    return Export(**data)


def test_export_validates_and_serializes():
    export = make_export()
    assert export.schema_version == "1.0"
    assert export.created_at.tzinfo is not None
    payload = json.loads(export.model_dump_json())
    assert payload["schema_version"] == "1.0"
    assert payload["source"] == "resanta.ru"
    assert payload["category"]["name"] == "Перфораторы"
    assert payload["products"][0]["source_url"] == VALID_URL


def test_export_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        make_export(created_at=datetime(2026, 7, 28, 12, 0, 0))


def test_error_record_and_errors_export():
    record = ErrorRecord(source_url=VALID_URL, stage="product", error="timeout")
    assert record.ts.tzinfo is not None
    errors = ErrorsExport(source="resanta.ru", errors=[record])
    assert errors.schema_version == "1.0"
    payload = json.loads(errors.model_dump_json())
    assert payload["errors"][0]["stage"] == "product"
    assert payload["errors"][0]["error"] == "timeout"


def test_error_record_bad_stage_rejected():
    with pytest.raises(ValidationError):
        ErrorRecord(source_url=VALID_URL, stage="bogus", error="x")


# --- изображения (ИЗО-02) ------------------------------------------------


def test_product_card_without_images_backward_compatible():
    """Карточка БЕЗ ключа images валидна: все уже собранные выгрузки читаются.

    Именно этот тест — доказательство обратной совместимости: экспорты Phase 2
    поля images не содержат вовсе.
    """
    raw = {
        "source_url": VALID_URL,
        "name": "Перфоратор П-30/900К",
        "attributes": {"Мощность, Вт": "900"},
    }
    card = ProductCard(**raw)
    assert card.images == []
    assert json.loads(card.model_dump_json())["images"] == []


def test_export_without_images_round_trip():
    """Старая выгрузка целиком (Export без images) читается и сериализуется."""
    payload = {
        "schema_version": "1.0",
        "source": "resanta.ru",
        "created_at": "2026-07-28T12:00:00+00:00",
        "category": {"name": "Перфораторы", "source_url": CATEGORY_URL},
        "products": [{"source_url": VALID_URL, "name": "П-30/900К"}],
    }
    export = Export(**payload)
    assert export.products[0].images == []


def test_product_card_images_parsed():
    card = make_card(
        images=[
            {"url": "https://resanta.ru/img/a.jpg", "is_main": True, "alt": "  Перфоратор  "},
            {"url": "https://resanta.ru/img/b.jpg"},
        ]
    )
    assert [i.url for i in card.images] == [
        "https://resanta.ru/img/a.jpg",
        "https://resanta.ru/img/b.jpg",
    ]
    assert card.images[0].is_main is True
    assert card.images[0].alt == "Перфоратор"
    assert card.images[1].is_main is False and card.images[1].alt is None


def test_product_card_images_relative_url_rejected():
    """Тот же валидатор, что у source_url: относительный путь не проходит."""
    with pytest.raises(ValidationError):
        make_card(images=[{"url": "/img/a.jpg"}])


def test_product_card_images_deduplicated_by_url():
    card = make_card(
        images=[
            {"url": "https://resanta.ru/img/a.jpg", "is_main": True},
            {"url": "https://resanta.ru/img/a.jpg"},
        ]
    )
    assert len(card.images) == 1


def test_product_card_images_single_main():
    """Источник пометил главными две — главной остаётся первая."""
    card = make_card(
        images=[
            {"url": "https://resanta.ru/img/a.jpg", "is_main": True},
            {"url": "https://resanta.ru/img/b.jpg", "is_main": True},
        ]
    )
    assert [i.is_main for i in card.images] == [True, False]
