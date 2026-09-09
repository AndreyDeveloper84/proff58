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
