"""Pydantic-схемы выгрузки парсера (Phase 2).

Цен в схемах нет и быть не должно. Значения атрибутов хранятся сырыми
(«как есть» с сайта): приведение единиц и типов — задача Phase 3. Единственная
очистка строк — strip + схлопывание пробельных последовательностей.
"""

import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

_WS_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    """strip + схлопывание пробельных последовательностей в один пробел."""
    return _WS_RE.sub(" ", value).strip()


def _validate_source_url(value: str) -> str:
    """Только абсолютные http/https URL: схема и хост обязательны."""
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"source_url должен быть абсолютным http(s) URL: {value!r}")
    return value


def _validate_aware_dt(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("дата/время должны быть timezone-aware (UTC)")
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProductCard(BaseModel):
    """Карточка товара-донора характеристик (без цен и фотографий)."""

    source_url: str
    name: str
    brand: str | None = None
    manufacturer_sku: str | None = None
    description: str | None = None
    # сырые значения как есть; ключ — исходная подпись поля с сайта
    attributes: dict[str, str] = Field(default_factory=dict)
    # сырая «краткая сводка» карточки (у Ресанты — носитель мощности)
    summary_raw: str | None = None

    @field_validator("source_url")
    @classmethod
    def _check_source_url(cls, value: str) -> str:
        return _validate_source_url(value)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("name не должно быть пустым после очистки")
        return value

    @field_validator("brand", "manufacturer_sku", "description", "summary_raw")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value) or None

    @field_validator("attributes")
    @classmethod
    def _clean_attributes(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, val in value.items():
            clean_key = _clean_text(key)
            clean_val = _clean_text(val)
            if not clean_key:
                raise ValueError("пустая подпись атрибута недопустима")
            if not clean_val:
                raise ValueError(f"пустое значение атрибута «{clean_key}» недопустимо")
            cleaned[clean_key] = clean_val
        return cleaned


class CategoryRef(BaseModel):
    """Ссылка на категорию-источник в выгрузке."""

    name: str
    source_url: str

    @field_validator("source_url")
    @classmethod
    def _check_source_url(cls, value: str) -> str:
        return _validate_source_url(value)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("name категории не должно быть пустым")
        return value


class Export(BaseModel):
    """Выгрузка карточек одной категории одного источника."""

    schema_version: Literal["1.0"] = "1.0"
    source: str
    created_at: datetime = Field(default_factory=_utcnow)
    category: CategoryRef
    products: list[ProductCard] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def _clean_source(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("source не должно быть пустым")
        return value

    @field_validator("created_at")
    @classmethod
    def _check_created_at(cls, value: datetime) -> datetime:
        return _validate_aware_dt(value)


class ErrorRecord(BaseModel):
    """Одна ошибка обхода: на каком URL и на какой стадии случилась."""

    source_url: str
    stage: Literal["category", "product"]
    error: str
    ts: datetime = Field(default_factory=_utcnow)

    @field_validator("source_url")
    @classmethod
    def _check_source_url(cls, value: str) -> str:
        return _validate_source_url(value)

    @field_validator("error")
    @classmethod
    def _clean_error(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("error не должно быть пустым")
        return value

    @field_validator("ts")
    @classmethod
    def _check_ts(cls, value: datetime) -> datetime:
        return _validate_aware_dt(value)


class ErrorsExport(BaseModel):
    """Журнал ошибок обхода одного источника."""

    schema_version: Literal["1.0"] = "1.0"
    source: str
    created_at: datetime = Field(default_factory=_utcnow)
    errors: list[ErrorRecord] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def _clean_source(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("source не должно быть пустым")
        return value

    @field_validator("created_at")
    @classmethod
    def _check_created_at(cls, value: datetime) -> datetime:
        return _validate_aware_dt(value)
