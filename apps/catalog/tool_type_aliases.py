"""Явный слой aliases ``legacy root name → live root name`` для ``enrich_tool_type``.

Контекст: ``tool_type_rules.json`` адресует category-блоки по строковому имени
корневой категории (см. ``ToolTypeRules``/``tool_type.py``). Часть корней сайта
были переименованы при переходе на v2-дерево (см.
``scratchpad/phase8/tool-type-rules-v1-v2-gap-report.md``), из-за чего блок
становится молча недостижим — ``top_name not in rule_categories`` без ошибки
и без записи. Решение владельца (``owner-decisions.md``
§STEP6-KEYWORDS-V1V2-DECISIONS, вариант B): явная таблица aliases вместо
fuzzy/substring-сопоставления.

Правила:

* alias — пара строк, точное совпадение (без ``normalize``/casefold/lower);
* legacy-имя alias обязано существовать среди блоков загруженного ruleset
  (13 текущих блоков не меняются) — иначе ``AliasConfigError`` (дрейф
  конфигурации);
* коллизия — одно live-имя закреплено за двумя разными legacy-блоками
  (включая случай, когда live-имя само по себе уже является отдельным
  прямым rule-блоком) — тоже ``AliasConfigError``;
* первая подтверждённая итерация — ровно 2 alias.
"""

from __future__ import annotations

ROOT_ALIASES: dict[str, str] = {
    "Спецодежда и защита": "Спецодежда и СИЗ",
    "Строительное и отделочное": "Строительный и отделочный инструмент",
}


class AliasConfigError(Exception):
    """Ошибка конфигурации aliases: коллизия или отсутствующий legacy-блок.

    Fail-fast: поднимается при загрузке, до любого обращения к БД.
    """


def resolve_live_to_legacy(
    rule_categories: set[str], aliases: dict[str, str] = ROOT_ALIASES
) -> dict[str, str]:
    """Построить lookup ``live root name → legacy category`` из явных aliases.

    ``rule_categories`` — множество имён категорий из загруженного
    ``tool_type_rules.json`` (``{c.category for c in rules.categories}``).
    Строгое совпадение строк, без нормализации: alias — это подтверждённое
    переименование, а не эвристика.
    """
    live_to_legacy: dict[str, str] = {}
    for legacy, live in aliases.items():
        if legacy not in rule_categories:
            raise AliasConfigError(
                f"alias_legacy_block_missing: legacy-блок {legacy!r} не найден среди "
                "rule-блоков tool_type_rules.json (дрейф конфигурации aliases)"
            )
        if live in rule_categories:
            raise AliasConfigError(
                f"alias_collision: live-имя {live!r} уже является собственным rule-блоком "
                f"и одновременно alias-целью для {legacy!r}"
            )
        existing = live_to_legacy.get(live)
        if existing is not None and existing != legacy:
            raise AliasConfigError(
                f"alias_collision: live-имя {live!r} назначено нескольким legacy-блокам: "
                f"{existing!r} и {legacy!r}"
            )
        live_to_legacy[live] = legacy
    return live_to_legacy
