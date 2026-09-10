"""Подбор доноров для обрезанных названий внутри каталога (catalog_name_analogs).

Опасность здесь одна: принять за донора позицию другой серии и дописать чужой
хвост. Поэтому проверок на отказ больше, чем на успех.
"""

import csv

import pytest
from django.core.management import call_command

from apps.catalog.models import Product

FULL = "Плашка М 6х0,5 класс точности 6g, сталь 9ХС, ГОСТ 9740-71"
# 1С рубит ровно по 50 символов; косметика прогона убирает висящий пробел.
CUT_RAW = FULL[:50]
CUT = CUT_RAW.strip()


def _rows(path):
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def cut_product(db):
    return Product.objects.create(
        name=CUT,
        original_name=CUT_RAW,  # ровно 50 символов — след обрезки 1С
        slug="plashka-m6",
        article="P-6",
    )


@pytest.mark.django_db
def test_donor_of_same_series_completes_the_tail(tmp_path, cut_product):
    """Числа остаются свои, хвост берётся у уцелевшего соседа по серии."""
    Product.objects.create(
        name="Плашка М 30х2,0 класс точности 6g, сталь 9ХС, ГОСТ 9740-71",
        original_name="Плашка М 30х2,0 класс точности 6g, сталь 9ХС, ГОСТ 9740-71",
        slug="plashka-m30",
        article="P-30",
    )
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)

    rows = _rows(out)
    assert len(rows) == 1
    assert rows[0]["name"] == "Плашка М 6х0,5 класс точности 6g, сталь 9ХС, ГОСТ 9740-71"
    assert rows[0]["source"] == "inferred"
    assert "донор" in rows[0]["evidence_url"]


@pytest.mark.django_db
def test_other_series_is_not_a_donor(tmp_path, cut_product):
    """Похожий по началу товар другой серии хвост не отдаёт."""
    Product.objects.create(
        name="Плашка М 30х2,0 класс точности 6g, сталь Р6М5, ТУ 2-035",
        original_name="Плашка М 30х2,0 класс точности 6g, сталь Р6М5, ТУ 2-035",
        slug="plashka-tu",
        article="P-TU",
    )
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    assert _rows(out) == []


@pytest.mark.django_db
def test_donor_must_continue_the_cut_word(tmp_path, cut_product):
    """Обрубок «ГОС» должен продолжаться в «ГОСТ», а не во что попало."""
    Product.objects.create(
        name="Плашка М 30х2,0 класс точности 6g, сталь 9ХС, левая резьба",
        original_name="Плашка М 30х2,0 класс точности 6g, сталь 9ХС, левая резьба",
        slug="plashka-levaya",
        article="P-L",
    )
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    assert _rows(out) == []


@pytest.mark.django_db
def test_already_restored_name_is_skipped(tmp_path, cut_product):
    """Имя, уже восстановленное из внешнего источника, второй раз не трогаем."""
    Product.objects.create(
        name="Плашка М 30х2,0 класс точности 6g, сталь 9ХС, ГОСТ 9740-71",
        original_name="Плашка М 30х2,0 класс точности 6g, сталь 9ХС, ГОСТ 9740-71",
        slug="plashka-m30",
        article="P-30",
    )
    cut_product.content_field_sources = {"name": "web"}
    cut_product.save()
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    assert _rows(out) == []


@pytest.mark.django_db
def test_ambiguous_tail_is_refused(tmp_path):
    """Если доноры дают разные хвосты — не достраиваем ничего.

    У молотка ЗУБР вес зависит от размера бойка: 35 мм — 450 г, 47 мм — 680 г.
    Когда обрыв пришёлся ровно перед весом, какой из хвостов наш — по названию
    не понять. Подставить чужое число в карточку хуже, чем оставить обрыв.
    """
    full = "Молоток безынерционный ЗУБР Профессионал 40мм, вес 680г"
    cut_raw = full[:50]
    assert cut_raw.split()[-1] == "вес", cut_raw  # обрыв пришёлся перед числом
    Product.objects.create(
        name=cut_raw.strip(),
        original_name=cut_raw,
        slug="molotok-40",
        article="M-40",
    )
    for size, weight in (("35мм", "450г"), ("47мм", "680г")):
        Product.objects.create(
            name=f"Молоток безынерционный ЗУБР Профессионал {size}, вес {weight}",
            original_name=f"Молоток безынерционный ЗУБР Профессионал {size}, вес {weight}",
            slug=f"molotok-{size}",
            article=f"M-{size}",
        )

    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    assert _rows(out) == []


@pytest.mark.django_db
def test_web_restored_name_becomes_donor(tmp_path):
    """Найденное в интернете имя закрывает остальных членов серии.

    Иначе на каждую позицию пришлось бы искать отдельно: у обрезанных строка 1С
    так и остаётся обрезанной, и по ней донора не отличить от собрата.
    """
    full = "Бур 5х165х100 SDS+ Hitachi 4 кромки цельный твердосплавный"
    Product.objects.create(  # этот уже восстановлен по карточке производителя
        name=full,
        original_name=full[:50],
        slug="bur-5",
        article="783202",
        content_field_sources={"name": "web"},
    )
    other = "Бур 6х215х150 SDS+ Hitachi 4 кромки цельный твердосплавный"
    cut = Product.objects.create(
        name=other[:50].strip(),
        original_name=other[:50],
        slug="bur-6",
        article="783210",
    )

    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    rows = _rows(out)
    assert [r["product_id"] for r in rows] == [str(cut.pk)]
    assert rows[0]["name"] == other


@pytest.mark.django_db
def test_inferred_name_does_not_become_donor(tmp_path):
    """Достройка по аналогу донором не становится — иначе ошибка расползётся."""
    full = "Бур 5х165х100 SDS+ Hitachi 4 кромки цельный твердосплавный"
    Product.objects.create(
        name=full,
        original_name=full[:50],
        slug="bur-5",
        article="783202",
        content_field_sources={"name": "inferred"},
    )
    other = "Бур 6х215х150 SDS+ Hitachi 4 кромки цельный твердосплавный"
    Product.objects.create(
        name=other[:50].strip(), original_name=other[:50], slug="bur-6", article="783210"
    )
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    assert _rows(out) == []


@pytest.mark.django_db
def test_longer_tail_wins_when_variants_agree(tmp_path):
    """«сталь Р6М5К5» и «сталь Р6М5К5, ГОСТ 10902» — не конфликт, а подробность.

    В каталоге у одной серии свёрл часть позиций названа короче. Берём самый
    полный вариант, раз остальные — его начало.
    """
    full = "Сверло ц/х ф3,8 сред серия класс А,, легир кобальт, сталь Р6М5К5, ГОСТ 10902"
    cut = Product.objects.create(
        name=full[:50].strip(), original_name=full[:50], slug="sverlo-38", article="S-38"
    )
    for size, tail in (
        ("ф2,3", "сталь Р6М5К5, ГОСТ 10902"),
        ("ф15,5", "сталь Р6М5К5"),
    ):
        name = f"Сверло ц/х {size} сред серия класс А,, легир кобальт, {tail}"
        Product.objects.create(
            name=name, original_name=name, slug=f"sverlo-{size}", article=f"S-{size}"
        )

    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    rows = _rows(out)
    assert [r["product_id"] for r in rows] == [str(cut.pk)]
    assert rows[0]["name"] == full


@pytest.mark.django_db
def test_article_prefix_picks_the_right_series(tmp_path):
    """Артикул разводит серии, которые по названию неразличимы.

    У кругов MD-STARS («GR7MD…») и SKYWER хвосты разные, а начало названия
    совпадает до последнего слова. Без артикула пришлось бы отказаться от обеих.
    """
    cut_full = "Круг алмазный отрезной 180х1,4х7х22 1A1R Мокрорез GRANIT ECONOM MD-STARS"
    cut = Product.objects.create(
        name=cut_full[:50].strip(),
        original_name=cut_full[:50],
        slug="krug-180",
        article="GR7MD18022",
    )
    Product.objects.create(  # та же серия — её хвост и нужен
        name="Круг алмазный отрезной 200х1,4х7х22,2 1A1R Мокрорез GRANIT ECONOM MD-STARS",
        original_name="Круг алмазный отрезной 200х1,4х7х22,2 1A1R Мокрорез GRANIT ECONOM MD-STARS",
        slug="krug-200",
        article="GR7MD20022",
    )
    Product.objects.create(  # чужая серия с другим хвостом
        name="Круг алмазный отрезной 230х1,6х7х25,4 1A1R Мокрорез GRANITE Гранит, базальт",
        original_name="Круг алмазный отрезной 230х1,6х7х25,4 1A1R Мокрорез GRANITE Гранит, базальт",
        slug="krug-230",
        article="SK-UUS23025",
    )

    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    rows = _rows(out)
    assert [r["product_id"] for r in rows] == [str(cut.pk)]
    assert rows[0]["name"].endswith("GRANIT ECONOM MD-STARS")


@pytest.mark.django_db
def test_tail_with_measurements_is_refused(tmp_path):
    """Хвост с характеристикой принадлежит позиции, а не серии.

    У трансформатора НТС-1,6У2 мощность 1,6 кВА и вес 35 кг — свои, и донор
    соседней модели подставил бы их модели НТС-2,5У2, у которой они другие.
    """
    full = "Трансформатор понижающий НТС-2,5У2 с 380В на 42В 3фазн. 2,5кВА 35кг"
    Product.objects.create(
        name=full[:50].strip(), original_name=full[:50], slug="ntc-25", article="NTC-25"
    )
    Product.objects.create(
        name="Трансформатор понижающий НТС-1,6У2 с 380В на 42В 3фазн. 1,6кВА 35кг",
        original_name="Трансформатор понижающий НТС-1,6У2 с 380В на 42В 3фазн. 1,6кВА 35кг",
        slug="ntc-16",
        article="NTC-16",
    )
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    assert _rows(out) == []


@pytest.mark.django_db
def test_break_on_word_boundary_is_handled(tmp_path):
    """Обрыв может прийтись ровно на пробел — последнее слово тогда целое.

    Прежний подбор всегда отбрасывал последнее слово как обрубок и терял такие
    позиции: на стенде их оказалось 286.
    """
    full = "Метчик м/р М10х1,25 левый сталь Р6М5 ГОСТ 3266-81 комплект"
    cut_raw = full[:50]
    assert cut_raw.endswith("81 "), repr(cut_raw)
    cut = Product.objects.create(
        name=cut_raw.strip(), original_name=cut_raw, slug="metchik-10", article="M-10"
    )
    Product.objects.create(
        name="Метчик м/р М12х1,5 левый сталь Р6М5 ГОСТ 3266-81 комплект",
        original_name="Метчик м/р М12х1,5 левый сталь Р6М5 ГОСТ 3266-81 комплект",
        slug="metchik-12",
        article="M-12",
    )
    out = tmp_path / "analogs.csv"
    call_command("catalog_name_analogs", f"--out={out}", verbosity=0)
    rows = _rows(out)
    assert [r["product_id"] for r in rows] == [str(cut.pk)]
    assert rows[0]["name"].endswith("комплект")
