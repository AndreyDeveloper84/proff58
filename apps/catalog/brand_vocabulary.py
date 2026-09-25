"""Общий словарь брендов каталога — единственный источник бренд-знания.

Файл данных: ``data/catalog_processing_rules/brand_vocabulary.json``.

Модуль намеренно **не импортирует Django и ORM**: словарём пользуется в том числе
:mod:`apps.catalog.taxonomy_audit`, который считает таксономию по файлам ``data/``
и обязан оставаться чистой логикой без БД. Пока загрузчик жил внутри
``scraped_import``, подключить его там было нельзя — тот тянет модели.

Потребители читают РАЗНЫЕ части словаря, и это не случайность:

* :mod:`apps.catalog.scraped_import` — ``canonical`` + ``aliases``. Маркеры
  совместимости сознательно НЕ применяет: для индекса матчинга товар,
  совместимый с двумя брендами, обязан быть виден карточкам обоих.
* :mod:`apps.catalog.brand_identity` (BRAND-02) — те же плюс
  ``compatibility_markers`` и ``series_exclusions``: там вопрос «кто произвёл»,
  и «Аккумулятор **для Makita**» произведён не Makita.
* :mod:`apps.catalog.taxonomy_audit` — только ``aliases`` и только для вопроса
  «является ли имя УЗЛА дерева брендом» (находка F4).

Один источник знания, разная семантика потребителей.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

BRAND_VOCABULARY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "catalog_processing_rules"
    / "brand_vocabulary.json"
)


@dataclass(frozen=True)
class BrandVocabulary:
    """Загруженный словарь: канонические имена, алиасы и режим сопоставления."""

    canonical_by_alias: dict[str, str]
    alias_patterns: tuple[tuple[str, re.Pattern], ...]  # (canonical, скомпилированный алиас)
    source_defaults: dict[str, str]
    # Маркеры совместимости отдаются КАК ЕСТЬ из файла: их семантику знает только
    # brand_identity (BRAND-02). Приводить их здесь к плоскому кортежу нельзя —
    # схема с классами маркеров превратилась бы в список ключей словаря.
    compatibility_markers: object
    series_exclusions: frozenset[str]
    mode: str

    def canonicals(self) -> list[str]:
        out: list[str] = []
        for canonical, _ in self.alias_patterns:
            if canonical not in out:
                out.append(canonical)
        return out


def _compile_alias(alias: str, mode: str) -> re.Pattern:
    """Алиас → шаблон. ``word`` требует границу слова с обеих сторон.

    Подстрочный режим оставлен только для сверки: он даёт ложные срабатывания
    («калибр» в «калибровочная», «луга» в «плуга», «koki» в «HiKOKI»), а
    множество совпадений по слову — строгое подмножество подстрочных, поэтому
    переход на ``word`` сужает выборку, а не ослабляет brand gate.
    """
    escaped = re.escape(alias)
    if mode == "substring":
        return re.compile(escaped)
    return re.compile(rf"(?<![a-zа-я0-9]){escaped}(?![a-zа-я0-9])")


def load_brand_vocabulary(path: Path | None = None) -> BrandVocabulary:
    data = json.loads((path or BRAND_VOCABULARY_PATH).read_text(encoding="utf-8"))
    mode = (data.get("matching") or {}).get("mode", "word")
    canonical_by_alias: dict[str, str] = {}
    patterns: list[tuple[str, re.Pattern]] = []
    source_defaults: dict[str, str] = {}
    for entry in data.get("brands", []):
        canonical = entry["canonical"]
        for alias in entry.get("aliases", []):
            low = alias.lower()
            canonical_by_alias[low] = canonical
            patterns.append((canonical, _compile_alias(low, mode)))
        for source in entry.get("source_default_for", []):
            source_defaults[source] = canonical
    return BrandVocabulary(
        canonical_by_alias=canonical_by_alias,
        alias_patterns=tuple(patterns),
        source_defaults=source_defaults,
        compatibility_markers=data.get("compatibility_markers", []),
        series_exclusions=frozenset(s.lower() for s in data.get("series_exclusions", [])),
        mode=mode,
    )


BRAND_VOCABULARY = load_brand_vocabulary()
