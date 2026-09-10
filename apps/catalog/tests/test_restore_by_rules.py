"""Достройка обрезанных названий по правилам (catalog_restore_by_rules).

Правило работает сразу по сотням позиций, поэтому проверок на отказ здесь
больше, чем на успех: одна ошибочная регулярка испортит всю серию разом.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.catalog.models import Product

FULL = "Плашка М 6х0,5 класс точности 6g, сталь 9ХС, ГОСТ 9740-71"
CUT_RAW = FULL[:50]


@pytest.fixture
def cut(db):
    return Product.objects.create(
        name=CUT_RAW.strip(), original_name=CUT_RAW, slug="plashka-6", article="P-6"
    )


@pytest.mark.django_db
def test_rule_completes_the_series(cut):
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == FULL
    assert cut.content_field_sources["name"] == "rules"


@pytest.mark.django_db
def test_dry_run_writes_nothing(cut):
    before = cut.name
    call_command("catalog_restore_by_rules", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == before


@pytest.mark.django_db
def test_untouched_names_are_not_rewritten(db):
    """Правило работает только по обрезанным: у остальных хвост не терялся."""
    whole = Product.objects.create(
        name="Плашка М 8х1,0 класс точности 6g, сталь 9ХС",
        original_name="Плашка М 8х1,0 класс точности 6g, сталь 9ХС",  # не 50 символов
        slug="plashka-8",
        article="P-8",
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    whole.refresh_from_db()
    assert whole.name == "Плашка М 8х1,0 класс точности 6g, сталь 9ХС"


@pytest.mark.django_db
def test_name_from_web_is_not_overwritten(cut):
    """Найденное в карточке производителя правило поверх не кладёт."""
    cut.name = "Плашка М 6х0,5, из карточки производителя"
    cut.content_field_sources = {"name": "web"}
    cut.save()
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == "Плашка М 6х0,5, из карточки производителя"


@pytest.mark.django_db
def test_single_rule_can_be_selected(cut, tmp_path):
    call_command("catalog_restore_by_rules", "--rule=sverlo-cx-sred-gost10902", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == CUT_RAW.strip()  # плашку это правило не трогает


def test_every_rule_has_justification():
    """Без обоснования правило принимать нельзя: оно правит сотни карточек разом."""
    data = json.loads(
        (Path(settings.BASE_DIR) / "data" / "name_restore_rules.json").read_text(encoding="utf-8")
    )
    for rule in data["rules"]:
        assert rule.get("note"), f"{rule['id']}: нет пояснения, откуда взят хвост"
        assert 0 < float(rule["confidence"]) <= 1


@pytest.mark.django_db
def test_gost_year_is_taken_from_catalog():
    """«… ГОСТ 3266» → год берётся из целых названий той же номенклатуры."""
    full = "Метчик м/р М10х1,25 левый сталь Р6М5 ГОСТ 3266-81 длинный"
    cut_raw = full[:50]
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="metchik-10", article="M-10"
    )
    Product.objects.create(  # целое название — источник года
        name="Метчик м/р М12х1,5 левый сталь Р6М5 ГОСТ 3266-81",
        original_name="Метчик м/р М12х1,5 левый сталь Р6М5 ГОСТ 3266-81",
        slug="metchik-12",
        article="M-12",
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name.endswith("ГОСТ 3266-81")


@pytest.mark.django_db
def test_gost_year_is_refused_when_editions_differ():
    """Две редакции стандарта в каталоге — какая наша, по названию не понять."""
    full = "Сверло ц/х ф8,0 средняя серия сталь Р6М5 по ГОСТ 10902"
    cut_raw = full[:50]
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="sverlo-gost", article="S-G"
    )
    for year, size in (("77", "10"), ("64", "12")):
        Product.objects.create(
            name=f"Сверло ц/х ф{size},0 сталь Р6М5 ГОСТ 10902-{year}",
            original_name=f"Сверло ц/х ф{size},0 сталь Р6М5 ГОСТ 10902-{year}",
            slug=f"sverlo-{size}",
            article=f"S-{size}",
        )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == cut_raw.strip()


@pytest.mark.django_db
def test_dangling_paren_is_cut_off():
    """Оборванная скобка снимается — дописать перечень кодов нечем."""
    full = "Бензопровод в сборе (OLD 223-0097A-90/6692429/6688603) Hitachi"
    cut_raw = full[:50]
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="benzoprovod", article="B-1"
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == "Бензопровод в сборе"
    # Исходная строка 1С цела: коды не потеряны совсем.
    assert cut.original_name == cut_raw


@pytest.mark.django_db
def test_number_at_the_end_is_kept():
    """Число в конце не срезаем: это может быть значащий размер."""
    full = "Домкрат 2 т гидравлический подкатной T30, 135-330 мм"
    cut_raw = full[:50]
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="domkrat", article="D-1"
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name.endswith("135-330")


@pytest.mark.django_db
def test_unit_of_measure_is_not_trimmed():
    """«ход штока 60 м» — «м» здесь единица измерения, а не обрубок слова."""
    full = "Домкрат 30 т гидравлический низкий, ход штока 60 мм"
    cut_raw = full[:50]
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="domkrat-30", article="D-30"
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name.endswith("60 м")


@pytest.mark.django_db
def test_dangling_is_trimmed_until_clean():
    """Одного прохода мало: «(без полиспаста) с к» оставляло висячее «с»."""
    full = "Лебедка ручная ЛР-1 г/п 0,5 т (без полиспаста) с крюком"
    cut_raw = full[:50]
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="lebedka", article="L-1"
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == "Лебедка ручная ЛР-1 г/п 0,5 т (без полиспаста)"


@pytest.mark.django_db
def test_rpm_tail_is_completed_not_trimmed():
    """«150об/» достраивается до «об/мин», а не теряет слэш при уборке."""
    # 1С рубит ровно по 50 символов; подгоняем строку так, чтобы обрыв пришёлся
    # на единицу скорости.
    cut_raw = "Отвертка аккумуляторная СПЕЦ БАО-3,6-2 3,6В 150об/"
    assert len(cut_raw) == 50 and cut_raw.endswith("об/"), len(cut_raw)
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="otvertka-spec", article="O-1"
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name.endswith("об/мин")


@pytest.mark.django_db
def test_no_battery_note_is_restored():
    """«(без аккум и зар. ус» — уточнение возвращается целиком, а не срезается.

    Покупатель обязан увидеть, что инструмент продаётся без батареи и
    зарядного устройства, до того как положит его в корзину.
    """
    cut_raw = "Пила сабельная аккум. CR14DSL-T4; 14,4 V, (без акк"
    assert len(cut_raw) == 50, len(cut_raw)
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="pila-cr14", article="CR-14"
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == "Пила сабельная аккум. CR14DSL-T4; 14,4 V (без аккумулятора и ЗУ)"


@pytest.mark.django_db
def test_no_battery_note_repairs_earlier_trim():
    """Если уборка уже срезала уточнение, правило возвращает его обратно."""
    cut_raw = "Пила сабельная аккум. CR18DSL-T4; 18,0 V, (без акк"
    cut = Product.objects.create(
        name="Пила сабельная аккум. CR18DSL-T4; 18,0 V",  # уже урезано прежней уборкой
        original_name=cut_raw,
        slug="pila-cr18",
        article="CR-18",
        content_field_sources={"name": "rules"},
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name.endswith("(без аккумулятора и ЗУ)")
