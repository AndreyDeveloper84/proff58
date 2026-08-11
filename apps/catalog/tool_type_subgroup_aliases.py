"""Явный слой aliases ``legacy subgroup identity → live leaf category name(s)``
для категорий с ``extraction == "inherit_1c_subgroup"`` (сегодня — ровно одна:
``"Оснастка и расходники"``).

Контекст: подгруппа 1С в этой стратегии — это ``cat.name`` (имя ЛИСТОВОЙ
категории сайта товара), а не поле 1С ``source_group``
(``osnastka-mechanism-preflight-report.md``). Дерево категорий сайта разошлось
с историческими именами подгрупп в ``tool_type_rules.json`` (переименования,
слияния листьев) — точное совпадение только у 18/183 (9,8%) непокрытых на
момент находки. Решение владельца (окно ENRICH-WRITE-PATH-HARDENING,
2026-08-03): явная таблица aliases вместо fuzzy-сопоставления, СТРОГО только
для подтверждённых по составу листа случаев с явным лидером — см.
``enrich-write-path-hardening-close-report.md`` за разбор кандидатов.

Правила (по аналогии с ``tool_type_aliases.ROOT_ALIASES``):

* alias — legacy-подгруппа (``rule.subgroup`` override ИЛИ ``rule.tool_type``
  базового правила с пустым ``subgroup``) → один или несколько live-имён
  листовых категорий, точное совпадение (без normalize/casefold);
* legacy-подгруппа обязана существовать среди известных подгрупп/базовых типов
  загруженного ruleset категории — иначе ``SubgroupAliasConfigError``;
* live-имя не должно само по себе уже резолвиться (через normalize) — иначе
  alias избыточен и это тоже ``SubgroupAliasConfigError``;
* live-имя не может быть закреплено за двумя разными legacy-подгруппами;
* НЕ мапится намеренно: ``"Круги"`` (id=82, 859 товаров) — подтверждённая
  смешанная корзина (найден даже водонагреватель); ``"Пилки и полотна"`` —
  два кандидата без явного лидера (``"Полотна ножовочные"``/``"Пилки для
  лобзика"``); ``"Отрезные и шлифовальные круги"`` — кандидат ``"Пильные
  диски"`` семантически иной инструмент (диск для пилы, не круг для УШМ);
  ``"Держатели, адаптеры и патроны"`` — сквозная категория адаптеров без
  единственной подгруппы-владельца; ``"Металлорежущий инструмент"`` —
  промежуточный узел с собственной прямой корзиной товаров (тот же риск-
  паттерн, что и «Круги»). Все — в owner-decision списке close-report,
  не здесь.
"""

from __future__ import annotations

from apps.catalog.tool_type import normalize

SUBGROUP_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "Оснастка и расходники": {
        # «Пики, долота и зубила» (id=100) — переименованный лист, состав
        # подтверждён (Долото/Пика SDS+/SDS-MAX), явный лидер.
        "Пики и долота": ("Пики, долота и зубила",),
        # «Алмазные круги» — кластер из 3 листьев (родитель + 2 дочерних),
        # состав подтверждён («Круг алмаз. отрез.», «Чашка алмазная»).
        "Алмазные круги": ("Алмазная оснастка", "Диски", "Чашки"),
        # «Мешки-пылесборники» (id=106) — синоним базового «Мешки для
        # пылесосов», единственный кандидат, состав подтверждён.
        "Мешки для пылесосов": ("Мешки-пылесборники",),
    },
}


class SubgroupAliasConfigError(Exception):
    """Ошибка конфигурации subgroup aliases: коллизия, избыточность или
    отсутствующая legacy-подгруппа. Fail-fast: поднимается при загрузке,
    до любого обращения к БД (как ``tool_type_aliases.AliasConfigError``)."""


def known_subgroup_identities(category_rules) -> set[str]:
    """Подгруппы/базовые типы, которые ``ToolTypeRules.extract`` резолвит уже
    сегодня без всякого alias: override-подгруппы (``rule.subgroup``) и
    базовые типы (``rule.tool_type`` правил с пустым ``subgroup``)."""
    identities: set[str] = set()
    for rule in category_rules.rules:
        identities.add(rule.subgroup if rule.subgroup else rule.tool_type)
    return identities


def resolve_live_subgroup_to_legacy(
    category: str,
    known_identities: set[str],
    aliases: dict[str, dict[str, tuple[str, ...]]] = SUBGROUP_ALIASES,
) -> dict[str, str]:
    """Построить lookup ``live leaf name → legacy subgroup identity`` для
    категории ``category`` из явных aliases. Строгое совпадение строк на
    входе (``aliases``), но коллизия с уже резолвящимися именами проверяется
    через ``normalize`` — ровно так, как их сравнивает движок."""
    normalized_known = {normalize(identity) for identity in known_identities}
    live_to_legacy: dict[str, str] = {}
    for legacy_subgroup, live_names in aliases.get(category, {}).items():
        if legacy_subgroup not in known_identities:
            raise SubgroupAliasConfigError(
                f"subgroup_alias_legacy_missing: legacy-подгруппа {legacy_subgroup!r} "
                f"не найдена среди подгрупп/базовых типов блока {category!r} "
                "(дрейф конфигурации subgroup aliases)"
            )
        for live in live_names:
            if normalize(live) in normalized_known:
                raise SubgroupAliasConfigError(
                    f"subgroup_alias_redundant: live-лист {live!r} уже резолвится "
                    f"напрямую (совпадает с {legacy_subgroup!r} или другой известной "
                    "подгруппой через normalize) — alias избыточен"
                )
            existing = live_to_legacy.get(live)
            if existing is not None and existing != legacy_subgroup:
                raise SubgroupAliasConfigError(
                    f"subgroup_alias_collision: live-лист {live!r} назначен нескольким "
                    f"legacy-подгруппам: {existing!r} и {legacy_subgroup!r}"
                )
            live_to_legacy[live] = legacy_subgroup
    return live_to_legacy
