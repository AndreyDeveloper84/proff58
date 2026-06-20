"""Приоритет источников значений характеристик (provenance).

Единый источник правды о том, какой источник «главнее». Правило: значение,
проставленное более авторитетным источником (ручной ввод, импорт 1С), НЕ
перезаписывается автоматическим (regex/ключевое слово/LLM). Здесь нет обращения
к БД — модуль используют и команда ``enrich_attributes``, и будущий AI-адаптер
(#62). Никаких «магических чисел» приоритета по коду — только отсюда.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Source(models.TextChoices):
    """Откуда взялось значение характеристики (поле ProductAttributeValue.source)."""

    MANUAL = "manual", _("Вручную")
    IMPORT_1C = "import_1c", _("Импорт 1С")
    NAME_REGEX = "name_regex", _("Regex по названию")
    NAME_KEYWORD = "name_keyword", _("Ключевое слово")
    LLM = "llm", _("AI / LLM")


# Ранг приоритета: больше — авторитетнее. Значение высшего ранга низшим не затирается.
RANK: dict[str, int] = {
    Source.MANUAL: 100,
    Source.IMPORT_1C: 80,
    Source.NAME_REGEX: 60,
    Source.NAME_KEYWORD: 40,
    Source.LLM: 20,
}


def rank(source: str | None) -> int:
    """Числовой ранг источника (неизвестный/пустой → 0)."""
    return RANK.get(source or "", 0)


def can_overwrite(existing_source: str | None, new_source: str) -> bool:
    """Можно ли записать значение ``new_source`` поверх ``existing_source``.

    Пусто (значения ещё нет) → можно. Иначе — только если новый источник не ниже
    по рангу. Равный ранг разрешён намеренно: повторный прогон того же источника
    обновляет значение (идемпотентность ``enrich_attributes``).
    """
    if not existing_source:
        return True
    return rank(new_source) >= rank(existing_source)
