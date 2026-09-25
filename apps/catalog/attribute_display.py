"""Порядок показа характеристик товара на витрине (DATA-01).

Раньше карточка списка сортировала характеристики по алфавиту и обрезала по лимиту:
у перфоратора первой шла не энергия удара, а то, чьё название раньше по алфавиту.
Порядок «по типу товара» задаёт курируемый ``data/card_attribute_order.json``:

* ``by_tool_type[<slug типа>]`` — что показывать первым у конкретного типа;
* ``default`` — общий рейтинг важности для покупателя (добор после переопределения);
* характеристики вне обоих списков — в конце, по названию;
* ``last`` (``tool_type``) — всегда последним: он дублирует название и раздел.

Один и тот же порядок отдают list- и detail-эндпоинты, поэтому карточка, быстрый
просмотр и страница товара совпадают по построению. Модуль не ходит в БД: работает по
уже загруженным (prefetch) значениям и не зависит от context сериализатора — забытый
context не может молча вернуть алфавит.

Почему не ``CategoryAttribute.sort_order``: загрузчик привязок его не заполняет
(везде 0), а у 28 блоков из 48 привязка живёт в корне раздела — порядок «по типу» из
него не получить. Почему не порядок блоков ``attribute_rules.json``: это порядок
ИЗВЛЕЧЕНИЯ (у дрелей там первой идёт масса), а не показа.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

TOOL_TYPE_SLUG = "tool_type"
_UNLISTED = 10_000
_LAST = 20_000


def _order_path() -> Path:
    return Path(settings.BASE_DIR) / "data" / "card_attribute_order.json"


@lru_cache(maxsize=1)
def load_order() -> dict:
    """Прочитать и провалидировать файл порядка. Кэшируется на процесс."""
    raw = json.loads(_order_path().read_text(encoding="utf-8"))
    default = list(raw.get("default") or [])
    by_tool_type = {k: list(v) for k, v in (raw.get("by_tool_type") or {}).items()}
    last = list(raw.get("last") or [])
    for name, slugs in [("default", default), ("last", last), *by_tool_type.items()]:
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"card_attribute_order.json: повтор slug в «{name}»")
    return {"default": default, "by_tool_type": by_tool_type, "last": last}


def _tool_type_slug(pavs) -> str | None:
    for pav in pavs:
        if pav.attribute.slug == TOOL_TYPE_SLUG and pav.value_option_id:
            return pav.value_option.slug or None
    return None


def ordered_pavs(pavs) -> list:
    """Значения характеристик одного товара в порядке показа (стабильная сортировка)."""
    pavs = list(pavs)
    order = load_order()
    override = order["by_tool_type"].get(_tool_type_slug(pavs) or "", [])
    rank: dict[str, int] = {}
    for slug in [*override, *order["default"]]:
        rank.setdefault(slug, len(rank))
    last = {slug: i for i, slug in enumerate(order["last"])}

    def key(pav):
        slug = pav.attribute.slug
        if slug in last:
            return (_LAST + last[slug], "")
        return (rank.get(slug, _UNLISTED), pav.attribute.name.casefold())

    return sorted(pavs, key=key)


def is_key_attribute(pav) -> bool:
    """«Ключевая» характеристика — та, по которой товар фильтруют или сравнивают.

    Один критерий для карточки и для блока основных параметров страницы товара.
    """
    return bool(pav.attribute.is_filterable or pav.attribute.is_comparable)
