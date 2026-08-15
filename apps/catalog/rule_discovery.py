"""Поиск кандидатов на блоки правил характеристик (read-only аналитика).

Зачем модуль: карта «какой tool_type характеризовать следующим» до сих пор
считалась разовыми скриптами. Через месяц каталог меняется, и её приходится
считать заново вручную. Здесь — та же арифметика, но как воспроизводимая часть
репозитория: чистые функции без обращения к БД, чтобы их можно было прогнать на
любом списке названий (тесты, песочница, стенд).

Модуль ничего не пишет: он только читает названия товаров и
``data/attribute_rules.json`` и предлагает, какой блок правил написать
следующим. Решение о записи — за оператором.

Состав:

* :data:`PATTERNS` — каталог частотных шаблонов в названиях 1С (размер ``AxB``,
  ``N мм``, ``N шт``, резьба ``М8``, гритность ``P40``, биты ``PH2`` …). У
  каждого шаблона две регулярки: ``naive`` — то, что напишет человек с первого
  раза, и ``guarded`` — та же мысль с границами слова. Разница между их
  попаданиями и есть измеримое число ложных срабатываний (см.
  :func:`scan_names`), а не абстрактное предупреждение «бывают ошибки».
* :func:`head_token` / :func:`corpus_heterogeneity` — признак «свалки»: тип, у
  которого названия не имеют общего ведущего слова, характеризовать нельзя,
  его надо сначала разобрать на подтипы.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

__all__ = [
    "PATTERNS",
    "Pattern",
    "PatternHit",
    "corpus_heterogeneity",
    "head_token",
    "scan_items",
    "scan_names",
]


@dataclass(frozen=True)
class Pattern:
    """Частотный шаблон в названии товара и предлагаемая под него характеристика.

    ``naive`` — регулярка «в лоб», которую пишут первой; ``guarded`` — она же с
    границами слова и отсечением соседних единиц измерения. Обе обязаны иметь
    одинаковый смысл: ``guarded`` — подмножество ``naive``. На этом строится
    подсчёт ложных срабатываний, поэтому расширять ``guarded`` за пределы
    ``naive`` нельзя.
    """

    key: str
    title: str
    attribute_slug: str
    attribute_name: str
    kind: str  # number | select | text
    unit: str
    naive: re.Pattern
    guarded: re.Pattern
    note: str = ""
    # Шаблон, значение которого у набора означает не характеристику предмета, а
    # состав набора: для nabory-* его надо переводить в piece_count.
    set_attribute_slug: str = ""


@dataclass
class PatternHit:
    """Итог сканирования одного шаблона по корпусу названий."""

    pattern: Pattern
    naive_hits: int = 0
    guarded_hits: int = 0
    examples: list[str] = field(default_factory=list)
    false_positive_examples: list[str] = field(default_factory=list)
    values: Counter = field(default_factory=Counter)
    # Ключи объектов, у которых сработала защищённая регулярка. Нужны там, где
    # агрегата мало: видимость оси считается по КАЖДОМУ товару (в какой он
    # категории, привязан ли к ней фасет), а не долей на весь тип.
    matched_keys: list = field(default_factory=list)

    @property
    def false_positives(self) -> int:
        """Названия, которые ловит наивная регулярка и отсекает защищённая."""
        return self.naive_hits - self.guarded_hits

    @property
    def false_positive_rate(self) -> float:
        return (self.false_positives / self.naive_hits) if self.naive_hits else 0.0

    def share(self, total: int) -> float:
        """Доля товаров типа, у которых шаблон срабатывает (защищённая версия)."""
        return (self.guarded_hits / total) if total else 0.0


# --- каталог шаблонов ------------------------------------------------------ #
#
# Порядок фиксирован: он же порядок колонок в отчёте, и от него зависят
# воспроизводимые числа. Добавление шаблона — изменение метрики, поэтому
# новый шаблон обязан приходить вместе с обновлением документации.

_UNIT_TAIL = r"(?![а-яёa-z])"


def _p(
    key: str,
    title: str,
    slug: str,
    name: str,
    kind: str,
    unit: str,
    naive: str,
    guarded: str,
    note: str = "",
    set_slug: str = "",
) -> Pattern:
    flags = re.IGNORECASE
    return Pattern(
        key=key,
        title=title,
        attribute_slug=slug,
        attribute_name=name,
        kind=kind,
        unit=unit,
        naive=re.compile(naive, flags),
        guarded=re.compile(guarded, flags),
        note=note,
        set_attribute_slug=set_slug,
    )


PATTERNS: tuple[Pattern, ...] = (
    _p(
        "size_pair",
        "размер AxB",
        "size_pair",
        "Размер (пара)",
        "text",
        "",
        r"(\d+(?:[.,]\d+)?)\s*[xх*]\s*(\d+(?:[.,]\d+)?)",
        # Пара — это два размера подряд, а не кусок тройной комбинации
        # «М8х10х12» и не «10х11х12 мм» из набора: третий множитель означает
        # диапазон, у которого одного значения не существует.
        r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*[xх*]\s*(\d+(?:[.,]\d+)?)(?![\s]*[xх*]\s*\d)(?![\d.,])",
        note="ключи/головки: «10х11» — пара размеров, не диапазон",
    ),
    _p(
        "mm",
        "N мм",
        "diameter",
        "Диаметр",
        "number",
        "мм",
        r"(\d+(?:[.,]\d+)?)\s*мм",
        r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*мм" + _UNIT_TAIL,
        note="у части типов это не диаметр, а длина/ширина — slug уточняется вручную",
    ),
    _p(
        "m",
        "N м",
        "length",
        "Длина",
        "number",
        "м",
        # Наивная версия читает «16 мм» и «2 мАч» как метры — ровно та ошибка,
        # ради которой в отчёте есть колонка ложных срабатываний (на стенде это
        # 188 ложных на 124 попадания у свёрл: «ф 3,2 мм» → «3,2 м»).
        r"(\d+(?:[.,]\d+)?)\s*м",
        r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*м" + _UNIT_TAIL,
        note="наивная версия читает «16 мм» и «2 мАч» как метры",
    ),
    _p(
        "pcs",
        "N шт",
        "package_quantity",
        "Фасовка",
        "number",
        "шт",
        r"(\d+)\s*шт",
        r"(?<![\d.,])(\d+)\s*шт" + _UNIT_TAIL,
        note="у наборов это piece_count (число предметов), а не фасовка",
        set_slug="piece_count",
    ),
    _p(
        "volt",
        "N В",
        "voltage",
        "Напряжение",
        "number",
        "В",
        r"(\d+(?:[.,]\d+)?)\s*в",
        r"(?<![\d.,])(\d{1,3}(?:[.,]\d+)?)\s*-?\s*(?:вольт|в)" + _UNIT_TAIL,
        note="наивная версия ловит любую букву «в» после числа",
    ),
    _p(
        "watt",
        "N Вт",
        "power",
        "Мощность",
        "number",
        "Вт",
        r"(\d+(?:[.,]\d+)?)\s*вт",
        r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*вт" + _UNIT_TAIL,
    ),
    _p(
        "inch",
        "дюймы",
        "drive_size",
        "Посадочный размер",
        "select",
        '"',
        r"(\d+/\d+|\d+)\s*[\"'”]",
        r"(?<![\d.,])(\d{1,2}/\d{1,2}|\d{1,2})\s*[\"'”]",
        note='1/2", 3/8" — присадка/квадрат; у шлангов и труб это диаметр',
    ),
    _p(
        "thread",
        "резьба М8",
        "thread",
        "Резьба",
        "text",
        "",
        r"м\s?(\d+(?:[.,]\d+)?)",
        # Резьба — «М» перед числом на границе слова и без третьего звена
        # «М8/10/12»: у такой комбинации одного значения нет.
        r"(?<![а-яёa-z\d])м\s?(\d{1,3}(?:[.,]\d+)?)(?:\s?[xх]\s?\d+(?:[.,]\d+)?)?"
        r"(?![\d./]*[/]\d)" + _UNIT_TAIL,
        note="наивная версия ловит «М» из «М12 мм», «MAX», «м» метров",
    ),
    _p(
        "grit",
        "гритность P40",
        "grit",
        "Зернистость",
        "number",
        "P",
        r"[pр]\s?(\d+)",
        r"(?<![а-яёa-z\d])[pр]\s?(\d{2,4})" + _UNIT_TAIL,
        note="кириллическая «Р» и латинская «P» — оба написания встречаются",
    ),
    _p(
        "bit",
        "бита PH2/PZ2/T20",
        "bit_type",
        "Тип шлица",
        "select",
        "",
        r"(ph|pz|t|sl|hex|torx)\s?(\d+)",
        r"(?<![а-яёa-z\d])(ph|pz|tx|t|sl|hex|torx)\s?-?\s?(\d{1,3})" + _UNIT_TAIL,
        note="наивная версия ловит «T» из моделей инструмента (TE-2, T400)",
    ),
    _p(
        "kg",
        "N кг",
        "weight",
        "Вес",
        "number",
        "кг",
        r"(\d+(?:[.,]\d+)?)\s*кг",
        r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*кг" + _UNIT_TAIL,
    ),
)

PATTERNS_BY_KEY = {p.key: p for p in PATTERNS}


def scan_items(items, patterns=PATTERNS, *, examples: int = 3) -> dict[str, PatternHit]:
    """Прогнать каталог шаблонов по парам ``(ключ, название)``.

    Возвращает ``{ключ шаблона: PatternHit}``. Считаются два числа на шаблон:
    попадания наивной регулярки и защищённой. Их разность — ложные
    срабатывания; примеры таких названий собираются отдельно, чтобы оператор
    видел, на чём именно ошибается регулярка, а не только счётчик.

    Ключи попаданий защищённой регулярки сохраняются в
    :attr:`PatternHit.matched_keys`: доля на весь тип не отвечает на вопрос
    «а этим конкретным товарам значение вообще будет видно», а поимённый список
    — отвечает.
    """
    hits = {p.key: PatternHit(pattern=p) for p in patterns}
    for key, name in items:
        text = name or ""
        for pattern in patterns:
            naive_match = pattern.naive.search(text)
            if naive_match is None:
                continue
            hit = hits[pattern.key]
            hit.naive_hits += 1
            guarded_match = pattern.guarded.search(text)
            if guarded_match is None:
                if len(hit.false_positive_examples) < examples:
                    hit.false_positive_examples.append(text)
                continue
            hit.guarded_hits += 1
            hit.matched_keys.append(key)
            hit.values[guarded_match.group(0).strip()] += 1
            if len(hit.examples) < examples:
                hit.examples.append(text)
    return hits


def scan_names(names, patterns=PATTERNS, *, examples: int = 3) -> dict[str, PatternHit]:
    """То же, что :func:`scan_items`, но по голому списку названий.

    Ключом становится порядковый номер названия — для вызовов, где привязки к
    товарам нет (тесты, разовые прогоны по выгрузке имён).
    """
    return scan_items(enumerate(names), patterns, examples=examples)


# --- признак разнородности корпуса ----------------------------------------- #

_WORD_RE = re.compile(r"[а-яёa-z]{3,}", re.IGNORECASE)


def head_token(name: str) -> str:
    """Ведущее слово названия — то, чем товар назван («Ключ», «Круг», «Бита»).

    Названия 1С начинаются с предмета, поэтому первое слово длиной ≥ 3 букв —
    дешёвый и устойчивый признак «об одном ли эти товары». Числа, артикулы и
    односимвольные предлоги отбрасываются.
    """
    match = _WORD_RE.search(name or "")
    return match.group(0).lower() if match else ""


@dataclass(frozen=True)
class Heterogeneity:
    """Мера разнородности корпуса названий одного типа."""

    total: int
    distinct_heads: int
    top_head: str
    top_head_count: int

    @property
    def dominance(self) -> float:
        """Доля самого частого ведущего слова. 1.0 — все товары названы одинаково."""
        return (self.top_head_count / self.total) if self.total else 0.0

    @property
    def head_ratio(self) -> float:
        """Число разных ведущих слов на товар. Ближе к 1 — все названия разные."""
        return (self.distinct_heads / self.total) if self.total else 0.0


def corpus_heterogeneity(names) -> Heterogeneity:
    """Посчитать разнородность корпуса по ведущим словам названий."""
    heads = Counter(head_token(name) for name in names if head_token(name))
    total = sum(heads.values())
    top_head, top_count = heads.most_common(1)[0] if heads else ("", 0)
    return Heterogeneity(
        total=total,
        distinct_heads=len(heads),
        top_head=top_head,
        top_head_count=top_count,
    )
