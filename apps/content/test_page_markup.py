"""Тесты разметки инфо-страниц.

Разметку пишет человек в админке, поэтому проверяем не «парсер разобрал», а что
он не мешает писать: строка с двоеточием остаётся текстом, забытый разделитель
не роняет секцию, а привычная разметка статей работает как раньше.
"""

from apps.content.page_markup import parse_page_body


def test_секция_без_типа_ведёт_себя_как_статья():
    sections = parse_page_body("## Условия\nОбычный абзац.\n\n- пункт\n- ещё\n")

    assert sections[0]["layout"] == ""
    assert [b["kind"] for b in sections[0]["blocks"]] == ["text", "list"]


def test_карточки_разбираются_в_пары():
    sections = parse_page_body(
        "## Способы получения\n:карточки\n"
        "- Самовывоз | Заберите на 1-м Онежском, 12\n"
        "- Курьер | Привезём в день заказа\n"
    )

    assert sections[0]["layout"] == "cards"
    assert sections[0]["items"] == [
        {"title": "Самовывоз", "text": "Заберите на 1-м Онежском, 12"},
        {"title": "Курьер", "text": "Привезём в день заказа"},
    ]
    # Список превратился в карточки и не должен продублироваться абзацами.
    assert sections[0]["blocks"] == []


def test_пункт_без_разделителя_не_теряется():
    sections = parse_page_body("## Шаги\n:шаги\n- Свяжитесь с нами\n")

    # Человек забыл «|» — это не повод потерять пункт или уронить страницу.
    assert sections[0]["items"] == [{"title": "Свяжитесь с нами", "text": ""}]


def test_вопросы_становятся_парами_вопрос_ответ():
    sections = parse_page_body("## Вопросы\n:вопросы\n- Когда привезут? | На следующий день\n")

    assert sections[0]["layout"] == "faq"
    assert sections[0]["items"][0]["title"] == "Когда привезут?"


def test_герой_собирает_картинку_и_кнопки():
    sections = parse_page_body(
        "## Доставка\n:герой\n"
        "бейдж: ДОСТАВКА ПО ПЕНЗЕ\n"
        "изображение: /info/delivery/van.webp\n"
        "кнопка: Перейти в каталог | /catalog\n"
        "кнопка-контур: Связаться | /#contacts\n"
        "Инструмент привезём сами.\n"
    )
    hero = sections[0]

    assert hero["layout"] == "hero"
    assert hero["meta"] == {"badge": "ДОСТАВКА ПО ПЕНЗЕ", "image": "/info/delivery/van.webp"}
    assert hero["buttons"] == [
        {"label": "Перейти в каталог", "href": "/catalog", "style": "solid"},
        {"label": "Связаться", "href": "/#contacts", "style": "outline"},
    ]
    assert hero["blocks"][0]["text"] == "Инструмент привезём сами."


def test_несколько_изображений_для_коллажа():
    sections = parse_page_body("## О нас\n:герой\nизображения: /a.webp | /b.webp | /c.webp\n")

    assert sections[0]["meta"]["images"] == ["/a.webp", "/b.webp", "/c.webp"]


def test_строка_с_двоеточием_остаётся_текстом():
    sections = parse_page_body("## Условия\nМощность: 800 Вт, вес: 3 кг.\n")

    # Иначе любая характеристика в тексте превращалась бы в настройку секции.
    assert sections[0]["meta"] == {}
    assert sections[0]["blocks"][0]["text"] == "Мощность: 800 Вт, вес: 3 кг."


def test_ключи_читаются_только_в_начале_секции():
    sections = parse_page_body("## Гарантия\nПервый абзац.\nтелефон: 8 800 600-44-99\n")

    assert sections[0]["meta"] == {}
    assert len(sections[0]["blocks"]) == 1


def test_контакты_и_карта_несут_свои_поля():
    sections = parse_page_body(
        "## Как проехать\n:карта\nадрес: Пенза, 1-й Онежский проезд, 12\nрежим: 09:00–20:00\n"
    )

    assert sections[0]["layout"] == "map"
    assert sections[0]["meta"]["address"] == "Пенза, 1-й Онежский проезд, 12"
    assert sections[0]["meta"]["hours"] == "09:00–20:00"


def test_вводная_часть_до_первого_заголовка_сохраняется():
    sections = parse_page_body("Вступление без заголовка.\n\n## Раздел\nТекст.\n")

    assert sections[0]["heading"] == ""
    assert sections[0]["blocks"][0]["text"] == "Вступление без заголовка."
    assert sections[1]["heading"] == "Раздел"


def test_пустой_текст_даёт_пустой_список():
    assert parse_page_body("") == []


def test_таблица_из_разметки_статей_работает():
    sections = parse_page_body("## Зоны\n| Зона | Цена |\n| Центр | бесплатно |\n")

    table = sections[0]["blocks"][0]
    assert table["kind"] == "table"
    assert table["head"] == ["Зона", "Цена"]
