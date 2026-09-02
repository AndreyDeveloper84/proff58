"""Разметка инфо-страниц: тот же текст из админки, но с типами секций.

Статьи (``article_markup``) — это поток абзацев, списков и врезок. Инфо-страницы
устроены иначе: у них есть шапка с картинкой и кнопками, сетки карточек,
нумерованные шаги, аккордеон вопросов, блок контактов. Структуру этих секций
задаёт вёрстка, а наполнение остаётся за человеком в админке — иначе каждая
правка телефона или цены доставки превращается в релиз.

Поэтому секция получает одну служебную строку — тип, и дальше пишется обычной
разметкой статей:

    ## Способы получения
    :карточки
    - Самовывоз | Заберите заказ на 1-м Онежском, 12
    - Курьер по Пензе | Привезём в течение дня

    ## Что делать
    :шаги
    - Свяжитесь с нами | Опишите неисправность по телефону
    - Подготовьте товар | Понадобится чек и упаковка

    ## Вопросы
    :вопросы
    - Когда привезут заказ? | Обычно на следующий день

Ключ-значение в начале секции задаёт то, чего в тексте нет: картинку, кнопки,
контакты. Неизвестные ключи не трогаем — строка «Мощность: 800 Вт» должна
остаться абзацем, а не стать настройкой.

    ## Доставка
    :герой
    бейдж: ДОСТАВКА ПО ПЕНЗЕ И ОБЛАСТИ
    изображение: /info/delivery/van.webp
    кнопка: Перейти в каталог | /catalog
    кнопка-контур: Связаться | /#contacts
    Инструмент привезём сами — по городу в день заказа.

Всё, что не разобрано как тип/ключ/пары, уходит в обычный разбор статьи:
абзацы, списки, врезки и таблицы работают ровно как там.
"""

from __future__ import annotations

from .article_markup import parse_body

HEADING = "## "

#: Служебная строка типа секции. По-русски: её пишет тот же человек, что и текст.
LAYOUTS = {
    ":герой": "hero",
    ":карточки": "cards",
    ":шаги": "steps",
    ":чеклист": "checklist",
    ":вопросы": "faq",
    ":контакты": "contacts",
    ":карта": "map",
    ":теги": "chips",
}

#: Ключи «ключ: значение». Всё остальное остаётся текстом — см. модульную строку.
META_KEYS = {
    "бейдж": "badge",
    "изображение": "image",
    "изображения": "images",
    "адрес": "address",
    "телефон": "phone",
    "почта": "email",
    "режим": "hours",
    "тон": "tone",
}
BUTTON_KEYS = {"кнопка": "solid", "кнопка-контур": "outline"}

#: Типы секций, где список — это пары «заголовок | текст», а не просто пункты.
PAIR_LAYOUTS = {"cards", "steps", "faq"}
SEPARATOR = "|"


def _split_pair(item: str) -> dict:
    title, _, text = item.partition(SEPARATOR)
    return {"title": title.strip(), "text": text.strip()}


def _parse_meta_line(line: str) -> tuple[str, str] | None:
    key, sep, value = line.partition(":")
    if not sep:
        return None
    key = key.strip().lower()
    value = value.strip()
    if not value:
        return None
    if key in META_KEYS or key in BUTTON_KEYS:
        return key, value
    return None


def _chunks(body: str) -> list[tuple[str, list[str]]]:
    """Разбить текст на секции по «## », сохранив вводную часть без заголовка."""
    out: list[tuple[str, list[str]]] = []
    heading, lines = "", []
    for raw in (body or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith(HEADING):
            if heading or lines:
                out.append((heading, lines))
            heading, lines = stripped[len(HEADING) :].strip(), []
            continue
        lines.append(raw)
    if heading or lines:
        out.append((heading, lines))
    return out


def parse_page_body(body: str) -> list[dict]:
    """Разобрать текст инфо-страницы в типизированные секции для витрины.

    Возвращает ``[{"layout", "heading", "meta", "buttons", "items", "blocks"}]``.
    ``layout`` пустой — обычная текстовая секция, как в статьях.
    """
    sections: list[dict] = []
    for heading, lines in _chunks(body):
        layout = ""
        meta: dict[str, str] = {}
        images: list[str] = []
        buttons: list[dict] = []
        rest: list[str] = []
        head_done = False  # служебные строки идут только до первого текста

        for raw in lines:
            stripped = raw.strip()
            if not stripped:
                if not rest:
                    continue  # пустые строки перед содержимым ничего не значат
                rest.append(raw)
                continue
            if not head_done and stripped.lower() in LAYOUTS:
                layout = LAYOUTS[stripped.lower()]
                continue
            parsed = _parse_meta_line(stripped) if not head_done else None
            if parsed is not None:
                key, value = parsed
                if key in BUTTON_KEYS:
                    label, _, href = value.partition(SEPARATOR)
                    buttons.append(
                        {
                            "label": label.strip(),
                            "href": href.strip(),
                            "style": BUTTON_KEYS[key],
                        }
                    )
                elif META_KEYS[key] == "images":
                    images = [part.strip() for part in value.split(SEPARATOR) if part.strip()]
                else:
                    meta[META_KEYS[key]] = value
                continue
            head_done = True
            rest.append(raw)

        # Всё неслужебное разбираем ровно так же, как статью: абзацы, списки,
        # врезки и таблицы не должны вести себя здесь иначе.
        blocks: list[dict] = []
        for parsed_section in parse_body("\n".join(rest)):
            blocks.extend(parsed_section["blocks"])

        items: list[dict] = []
        if layout in PAIR_LAYOUTS or layout in {"checklist", "chips"}:
            kept: list[dict] = []
            for block in blocks:
                if block["kind"] != "list":
                    kept.append(block)
                    continue
                if layout in PAIR_LAYOUTS:
                    items.extend(_split_pair(item) for item in block["items"])
                else:
                    items.extend({"title": item, "text": ""} for item in block["items"])
            blocks = kept

        if images:
            meta["images"] = images
        section = {
            "layout": layout,
            "heading": heading,
            "meta": meta,
            "buttons": buttons,
            "items": items,
            "blocks": blocks,
        }
        if heading or layout or blocks or items or meta or buttons:
            sections.append(section)
    return sections
