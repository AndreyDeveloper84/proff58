"""Preflight SELECT-опций для ``enrich_attributes`` (FOUNDATION-AXES-01, часть D).

Дефект, который закрывает модуль (аудит ``docs/catalog/2026-09-12-select-preflight-audit.md``):
движок отдаёт SELECT-значение как ``option_slug`` из правила, а команда резолвит его
через индекс ``AttributeOption`` из БД. Если ``load_attributes`` не выполнен, опции
в БД нет — и значение **молча** пропускалось: ни счётчика, ни ненулевого exit-кода,
``ImportRun`` со статусом ``done``. 2026-09-11 так исчезли 42 значения.

Контракт (решение владельца 2026-09-12):

* до ``ImportRun.create`` и до любого чтения товаров проверяется
  ``required_options ⊆ AttributeOption в БД`` — только для опций, которые
  **реально** требуются блоками текущего прогона (``selected_tt``), а не для
  всего словаря: отсутствующая опция в чужом блоке прогон не блокирует;
* нарушение — отказ и в dry-run, и в write (единый путь принятия решений);
  обходного флага для записи **нет**;
* derive-правило с ``set_option`` вне собственных ``options`` — тоже дефект
  словаря (движок вернул бы ``None`` молча), поднимается тем же preflight.

Модуль чистый: без Django-запросов, индекс опций передаётся снаружи (у команды он
уже загружен одним запросом), поэтому стоимость — O(пар атрибут·вариант) в памяти.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .attribute_extract import SELECT

#: Exit-код отказа preflight/контракта схемы. Совпадает с ``EXIT_INVALID`` gate-контура
#: (``rules_gate.py``): «вход невалиден, ничего не выполнялось».
EXIT_PREFLIGHT = 2


@dataclass(frozen=True)
class RequiredOption:
    """Вариант SELECT-оси, который правила выбранных блоков обещают записать."""

    attribute: str
    option: str
    value: str
    tool_types: tuple[str, ...]


@dataclass(frozen=True)
class MissingOption:
    """Требуемый вариант, которого нет в БД."""

    attribute: str
    option: str
    value: str
    tool_types: tuple[str, ...]

    def describe(self) -> str:
        return f"{self.attribute} · {self.option!r} («{self.value}») — блоки: " + ", ".join(
            self.tool_types
        )


class RulesetError(ValueError):
    """Дефект словаря правил, который движок иначе скрыл бы молчаливым ``None``."""


def required_select_options(raw: Mapping, tool_types: Iterable[str]) -> list[RequiredOption]:
    """Все пары (атрибут, вариант) SELECT-осей блоков ``tool_types`` из сырого словаря.

    Объединение считается **на атрибут**: ``tool_kind``/``material`` делят одну ось
    между десятками блоков, и одна и та же опция требуется многими из них — в
    отчёте она выводится один раз со списком блоков.

    ``derive.set_option`` обязан входить в ``options`` того же правила — иначе
    :class:`RulesetError` (дефект словаря, а не схемы БД).
    """
    wanted = set(tool_types)
    found: dict[tuple[str, str], dict] = {}
    for block in raw.get("tool_types", []):
        tt = block.get("tool_type", "")
        if tt not in wanted:
            continue
        for rule in block.get("attributes", []):
            if rule.get("kind") != SELECT:
                continue
            slugs = {o["slug"] for o in rule.get("options", [])}
            derive = rule.get("derive") or {}
            set_option = derive.get("set_option")
            if set_option is not None and set_option not in slugs:
                raise RulesetError(
                    f"блок {tt!r}, атрибут {rule.get('slug')!r}: derive.set_option "
                    f"{set_option!r} не объявлен в options {sorted(slugs)} — "
                    "движок вернул бы None молча."
                )
            for option in rule.get("options", []):
                key = (rule["slug"], option["slug"])
                entry = found.setdefault(key, {"value": option.get("value", ""), "tool_types": []})
                if tt not in entry["tool_types"]:
                    entry["tool_types"].append(tt)
    return [
        RequiredOption(attr, opt, entry["value"], tuple(entry["tool_types"]))
        for (attr, opt), entry in sorted(found.items())
    ]


def check_select_options(
    required: Iterable[RequiredOption], option_index: Mapping[str, Mapping[str, object]]
) -> list[MissingOption]:
    """Требуемые варианты, отсутствующие в ``option_index`` (``{attr: {option_slug: …}}``).

    Порядок детерминирован (атрибут, вариант) — список пригоден для сравнения
    между dry-run и write.
    """
    return [
        MissingOption(r.attribute, r.option, r.value, r.tool_types)
        for r in required
        if r.option not in option_index.get(r.attribute, {})
    ]


def format_missing(missing: list[MissingOption], *, required: int, tool_types: int) -> str:
    """Текст отказа: полный список, подсказка — ``load_attributes``. Обхода нет."""
    lines = [
        f"Preflight опций не пройден: {len(missing)} вариантов SELECT из attribute_rules.json "
        f"отсутствуют в БД (типов в выборке {tool_types}, проверено {required} пар "
        "атрибут·вариант):"
    ]
    lines.extend(f"  {m.describe()}" for m in missing)
    lines.append(
        "Эти значения были бы молча пропущены. Выполните `load_attributes --dry-run` → "
        "`load_attributes` и повторите прогон. Обходного флага нет."
    )
    return "\n".join(lines)
