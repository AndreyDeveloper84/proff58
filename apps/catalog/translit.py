"""Транслитерация кириллицы в латиницу для генерации slug значений EAV (P2).

Без внешних зависимостей: своя таблица RU→latin (домен каталога — русский),
поверх неё штатный Django ``slugify``. Используется командой backfill_option_slugs
для заполнения пустых ``AttributeOption.slug``.

Намеренно отделено от ``build_categories.transliterate`` (та живёт в management-команде,
домен — категории, таблица иная и завязана на ``Category``): здесь slug строится для
значений характеристик, без побочной зависимости от команд/моделей.
"""

from __future__ import annotations

import re

from django.utils.text import slugify

# Любой разделитель/пунктуация → пробел ДО slugify, чтобы «Насадки/адаптеры» давало
# «nasadki-adaptery», а не склеенное «nasadkiadaptery» (slugify сам удалил бы «/» без разделителя).
_SEPARATORS_RE = re.compile(r"[^0-9A-Za-z-]+")

# Однозначная таблица RU→latin (предсказуемая, читаемая латиница).
_RU_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def translit(value: str) -> str:
    """Заменить кириллические буквы латиницей по таблице; прочие символы — как есть."""
    out: list[str] = []
    for ch in value or "":
        mapped = _RU_LATIN.get(ch.lower())
        if mapped is None:
            out.append(ch)
        else:
            # title-case для многобуквенных: «Ж»→«Zh», а не «ZH» (на slug не влияет — он в нижнем).
            out.append(mapped.capitalize() if ch.isupper() else mapped)
    return "".join(out)


def slugify_value(value: str) -> str:
    """ЧПУ-slug значения: транслит кириллицы → нормализация разделителей → ``slugify``.

    Может вернуть "" (напр. «!!!») — тогда вызывающий код подставляет base «option».
    """
    latin = translit(value or "")
    return slugify(_SEPARATORS_RE.sub(" ", latin))
