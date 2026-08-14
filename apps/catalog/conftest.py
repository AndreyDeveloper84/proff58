"""Общие фикстуры тестов каталога.

Единственная задача — изолировать тесты от БОЕВОГО реестра карантина
(``data/attribute_quarantine.json``). Полтора десятка модулей зовут
``enrich_attributes`` без ``--path``, то есть на боевом каталоге данных; любая
запись боевого реестра ссылается на реальный ``product_id``, которого в тестовой
БД нет, и команда честно падает с ``CommandError`` (контракт P2: неизвестный
товар — ошибка, escape hatch не предусмотрен).

Поэтому по умолчанию все тесты каталога видят ПУСТОЙ реестр. Тесты самого
карантина (``test_attribute_quarantine.py``) работают через явный ``--quarantine``
и фикстуру не задевают, а боевой файл отдельно валидируется на схему тем же
модулем.
"""

from __future__ import annotations

import json

import pytest

from apps.catalog import attribute_quarantine

EMPTY_REGISTRY = {"version": attribute_quarantine.VERSION, "items": []}


@pytest.fixture(autouse=True)
def empty_attribute_quarantine(tmp_path_factory, monkeypatch):
    """Подменить путь реестра по умолчанию пустым временным файлом."""
    path = tmp_path_factory.getbasetemp() / "attribute_quarantine_empty.json"
    if not path.exists():
        path.write_text(json.dumps(EMPTY_REGISTRY), encoding="utf-8")
    monkeypatch.setattr(attribute_quarantine, "default_registry_path", lambda base: path)
    return path
