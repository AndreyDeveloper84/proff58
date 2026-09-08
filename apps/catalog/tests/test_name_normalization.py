"""Раскрытие сокращений в витринных названиях (apps.catalog.name_normalization).

Главный риск здесь — не «не раскрыли», а «раскрыли неправильно»: русское
прилагательное согласуется с существительным, и замена «удар.» → «ударный»
превратила бы «Дрель удар.» в «Дрель ударный». Поэтому тестов на согласование и
на отказ от раскрытия больше, чем на сам словарь.
"""

import pytest

from apps.catalog.name_normalization import card_name, normalize_name, tidy


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Род берётся из типа товара в начале названия.
        ("Гайковерт удар. DW 292 DeWalt", "Гайковерт ударный DW 292 DeWalt"),
        ("Дрель удар. Makita 8406C", "Дрель ударная Makita 8406C"),
        ("Сверло удар. 6 мм", "Сверло ударное 6 мм"),
        # Несколько сокращений подряд — все относятся к одному типу.
        (
            "Круг алмаз. отрез. 115х1,0х10х22,23 Turbo",
            "Круг алмазный отрезной 115х1,0х10х22,23 Turbo",
        ),
        # Сокращённый тип раскрывается до поиска рода.
        ("Перф. Bosch GBH 2-23REA; 710Вт", "Перфоратор Bosch GBH 2-23REA; 710Вт"),
        ("Шлифмаш вибр Bosch GSS 23A", "Шлифмашина вибрационная Bosch GSS 23A"),
        # Существительное в родительном падеже — отдельное правило, не прилагательное.
        (
            "Винтоверт аккум. ЗУБР GVB-250 без аккум. и ЗУ",
            "Винтоверт аккумуляторный ЗУБР GVB-250 без аккумулятора и ЗУ",
        ),
    ],
)
def test_expands_with_agreement(source, expected):
    assert normalize_name(source) == expected


def test_stops_at_first_unknown_word():
    """Цепочка обрывается, когда прилагательное относится уже к другому слову.

    «с алмаз. коронкой» — женский род, но узнать это в середине названия
    нечем. Оставить сокращение честнее, чем написать «с алмазный коронкой».
    """
    assert (
        normalize_name("Дрель удар. Makita 8406C с алмаз. коронкой")
        == "Дрель ударная Makita 8406C с алмаз. коронкой"
    )


def test_container_word_blocks_expansion():
    """«Набор комб. ключей» — комбинированные тут ключи, а не набор.

    Род первого слова к сокращению отношения не имеет, и раскрытие дало бы
    «Набор комбинированный ключей». Такие названия не трогаем.
    """
    assert normalize_name("Набор комб. ключей 6 пр., (6-17мм) Вихрь") == (
        "Набор комб. ключей 6 пр., (6-17мм) Вихрь"
    )


def test_screwdriver_only_with_dot():
    """«Шуруп.» — шуруповёрт (349 позиций), «Шуруп» без точки — метиз."""
    assert normalize_name("Шуруп. аккум. AEG BS18G3LI") == "Шуруповёрт аккумуляторный AEG BS18G3LI"
    assert normalize_name("Шуруп 3,9х19 св. оцинк") == "Шуруп 3,9х19 св. оцинк"


def test_abbreviation_before_type():
    """«Свар. аппарат» — сокращение стоит перед типом, а не после него."""
    assert normalize_name("Свар. аппарат BRIMA TIG 180P") == "Сварочный аппарат BRIMA TIG 180P"


def test_unknown_type_is_left_alone():
    """Незнакомый тип не запускает раскрытие: род угадывать не станем."""
    assert normalize_name("Штуковина удар. 5 мм") == "Штуковина удар. 5 мм"


def test_tidies_spacing_and_units():
    assert normalize_name("Головка шлиф.алмаз.D95 1200/1000") == (
        "Головка шлифовальная алмазная D95 1200/1000"
    )
    assert tidy("Бокорезы 140мм. силовые Knipex  0,16 кг.") == (
        "Бокорезы 140 мм силовые Knipex 0,16 кг"
    )
    assert tidy("Ключ 10 мм , CrV") == "Ключ 10 мм, CrV"


def test_degrees_and_grams_untouched():
    """«гр.» — и граммы, и градусы; различить регуляркой нельзя, поэтому не трогаем."""
    assert tidy('Адаптер 90гр. 1/2" BSP') == 'Адаптер 90гр. 1/2" BSP'
    assert tidy("Газ в баллоне МАПП ГАЗ 453гр") == "Газ в баллоне МАПП ГАЗ 453гр"


def test_card_name_keeps_abbreviations():
    """Карточке достаётся телеграфная запись — развёрнутая туда не помещается."""
    source = "Круг алмаз. отрез. 115х1,0х10х22,23  Turbo SUPREME"
    assert card_name(source) == "Круг алмаз. отрез. 115х1,0х10х22,23 Turbo SUPREME"
    assert normalize_name(source) != card_name(source)


def test_idempotent():
    """Повторный прогон ничего не меняет — команду можно запускать сколько угодно."""
    once = normalize_name("Круг алмаз. отрез. 115х1,0 Turbo")
    assert normalize_name(once) == once


def test_empty_and_short_names_survive():
    assert normalize_name("") == ""
    assert normalize_name("Ключ") == "Ключ"


# --- Правила, добавленные по замеру каталога (DRF-1600 → DRF-1602) ---


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Тип во множественном числе: своя форма согласования.
        ("Клещи обжим. КВТ ПК-16у", "Клещи обжимные КВТ ПК-16у"),
        ("Ножницы удар. по металлу 250мм", "Ножницы ударные по металлу 250мм"),
        ("Электроды свар. ОК-46 3мм", "Электроды сварочные ОК-46 3мм"),
        # Типы, которых не было в GENDER: под ними лежало 13 942 товара.
        ("Леска д/триммер. 2,4мм, 200м СЕБ", "Леска для триммера 2,4мм, 200м СЕБ"),
        ("Кисть плоская 50мм нат. щетина", "Кисть плоская 50мм нат. щетина"),
    ],
)
def test_plural_and_new_types(source, expected):
    assert normalize_name(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Слово после «д/» почти всегда уже в родительном падеже.
        ("Пилки д/лобзика JUW20 (5шт)", "Пилки для лобзика JUW20 (5шт)"),
        # Предлог раскрывается независимо от того, знаком ли нам тип товара.
        ("Мешок д/мусора 120л", "Мешок для мусора 120л"),
        # Обрубленное 1С окончание досклоняем по закрытому списку.
        ("Пена монтаж. д/пист. ЗУБР 750мл", "Пена монтажная для пистолета ЗУБР 750мл"),
    ],
)
def test_for_slash_expands(source, expected):
    assert normalize_name(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # Слэш здесь — маркировка, а не «для». Раскрытие исказило бы смысл.
        "Сверло ц/х ф18,0х191 Р4М2 ЗУБР МАСТЕР",
        "Метчик м/р М16х1,5 к-т сталь 9ХC ГОСТ 3266-81",
        "Строп СТП-4/4 серый г/п4т, длина 4м ЗУБР",
        "Перчатки х/б с ПВХ покрытием",
    ],
)
def test_marking_slash_is_untouched(source):
    assert normalize_name(source) == source


def test_slash_inside_word_is_not_a_preposition():
    """«ход/мин» содержит «д/мин»: без границы слова вышло бы «хо для мин»."""
    source = "Лобзик CJ90VST; 700Вт, 850-3000х/мин, ход 20мм"
    assert normalize_name(source) == source


def test_size_separator_unified():
    """Латинская «x» между цифрами → кириллическая: иначе поиск не находит.

    В каталоге 9 663 названия с кириллической «х» против 462 с латинской —
    меньшинство обречено не находиться никогда.
    """
    assert normalize_name('Бур 10x210мм "SDS-Plus" ЗУБР') == 'Бур 10х210мм "SDS-Plus" ЗУБР'


def test_cyrillic_inside_latin_marking_fixed():
    """«RВ18DLL», «CrМоV» — буквы-двойники не в том алфавите."""
    assert normalize_name("Воздуходувка аккум Hitachi RВ18DLL") == (
        "Воздуходувка аккумуляторная Hitachi RB18DLL"
    )
    assert tidy("Отвертка PH 2х100 мм CrМоV 1000В") == "Отвертка PH 2х100 мм CrMoV 1000В"


@pytest.mark.parametrize(
    "source",
    [
        # Кириллица здесь родная — правило одностороннее и такие слова не трогает.
        "Набор инструмента 141 пр. АвтоDело",
        "Круг лепестковый ЗУБР МАСТЕР P220",
    ],
)
def test_russian_words_keep_their_alphabet(source):
    assert normalize_name(source) == source


def test_article_tail_dropped_only_on_exact_match():
    """Хвост снимаем, лишь когда он в точности равен нашему артикулу."""
    assert normalize_name("Пружина 322890", article="322890") == "Пружина"
    assert normalize_name("Кожух защитный УШМ 125 338845", article="338845*") == (
        "Кожух защитный УШМ 125"
    )
    # Код производителя нашему артикулу не равен — по нему ищут, оставляем.
    assert (
        normalize_name("Щетки угольные АНАЛОГ 13-104 HITACHI 990021", article="T108741")
        == "Щетки угольные АНАЛОГ 13-104 HITACHI 990021"
    )


def test_article_tail_never_empties_the_name():
    """Название, целиком равное артикулу, схлопывать нельзя."""
    assert normalize_name("322890", article="322890") == "322890"


def test_truncated_name_is_not_invented():
    """1С обрезала хвост — додумывать его нормализация не имеет права (DRF-1604)."""
    source = "Воздуходувка аккум Hitachi RB18DLL; без аккум и за"
    assert normalize_name(source) == "Воздуходувка аккумуляторная Hitachi RB18DLL; без аккум и за"


def test_new_rules_are_idempotent():
    for source in (
        "Леска д/триммер. 2,4мм",
        "Бур 10x210мм SDS",
        "Воздуходувка аккум Hitachi RВ18DLL",
        "Клещи обжим. КВТ",
    ):
        once = normalize_name(source)
        assert normalize_name(once) == once


def test_size_separator_wins_over_marking():
    """«PH3х 50 мм» — здесь «х» размер, а не сбитая раскладка в маркировке.

    Слово «PH3х» состоит в основном из латиницы, и общее правило починки
    алфавита перевело бы «х» в латинскую «x» — ровно против правила выше,
    которое сводит разделитель размера к кириллице. Поэтому «х» выведена
    из-под починки маркировки.
    """
    assert normalize_name("Биты Kraftool PH3х 50 мм Optimum Line") == (
        "Биты Kraftool PH3х 50 мм Optimum Line"
    )
    assert normalize_name("Фонарь ЭРА PA-601 прожектор АЛЬФА 19хLED+24хLED") == (
        "Фонарь ЭРА PA-601 прожектор АЛЬФА 19хLED+24хLED"
    )


@pytest.mark.django_db
def test_command_is_idempotent_on_card_name():
    """Повторный прогон команды не должен разворачивать плитку.

    `card_name` считается от строки 1С (`original_name`), а не от витринного
    `name`: после первого прогона `name` уже развёрнут, и счёт от него стёр бы
    телеграфную запись, ради которой поле и заведено.
    """
    from django.core.management import call_command

    from apps.catalog.models import Product

    product = Product.objects.create(
        name="Круг алмаз. отрез. 115х1,0",
        original_name="Круг алмаз. отрез. 115х1,0",
        slug="krug-almaz-115",
        article="KR-115",
    )
    call_command("normalize_product_names", verbosity=0)
    product.refresh_from_db()
    assert product.name == "Круг алмазный отрезной 115х1,0"
    assert product.card_name == "Круг алмаз. отрез. 115х1,0"

    call_command("normalize_product_names", verbosity=0)
    after = Product.objects.get(pk=product.pk)
    assert after.name == product.name
    assert after.card_name == product.card_name


def test_service_prefix_stripped():
    """«яя» — служебная метка сортировки 1С, на витрине ей не место.

    В `name` её вычистили раньше руками, но в `original_name` она осталась у
    4 547 позиций, а плитка считается именно от исходника.
    """
    assert tidy("яяДомкрат 12 т гидравлический 230-469 СЕРВИС КЛЮЧ") == (
        "Домкрат 12 т гидравлический 230-469 СЕРВИС КЛЮЧ"
    )
    assert normalize_name("яяЛебедка ручная 0,9т, 10м") == "Лебедка ручная 0,9т, 10м"
    # Обычное слово, начинающееся на «я», не трогаем.
    assert normalize_name("Ящик метал. разноуровневый") == "Ящик металлический разноуровневый"
