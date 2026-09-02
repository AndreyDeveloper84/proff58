"""Загрузка изображений и характеристик из выгрузки парсера производителя.

Контур: `parser/` собрал карточки с сайта производителя → эта команда находит
наши товары по артикулу и заводит фотографии через `ImagePipeline`.

Почему матчинг по артикулу, а не по названию. У huter.su JSON-LD отдаёт `sku`,
буквально равный нашему `Product.article` (`70/6/2` = товар «Бензопила HUTER
BS-45»): на боевом прогоне 02.09.2026 совпали 64 из 70 наших товаров. Матчинг
по модели из названия, которым живёт `scraped_import` для характеристик, здесь
не нужен и был бы слабее — он даёт похожесть, а не равенство.

Инварианты, каждый закреплён тестом:

* dry-run по умолчанию — без `--apply` в БД не появляется ничего;
* `manual` неприкосновенен: он не может быть источником прогона;
* товар с `content_locked` не трогаем;
* совпадение только ПОЛНОЕ (после нормализации), подстрока запрещена;
* наш внутренний суффикс фасовки `_z01` снимается — у производителя его нет;
* повторный прогон не плодит дубли (идемпотентность держит `ImagePipeline`).
"""
from __future__ import annotations

import json

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Category,
    ImageSource,
    Product,
    ProductImage,
    ProductStatus,
)

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Стенды
# --------------------------------------------------------------------------- #

@pytest.fixture
def leaf():
    root = Category.add_root(name="Садовая техника", slug="sadovaya")
    return root.add_child(name="Бензопилы", slug="benzopily")


def make_product(leaf, *, article, name="Бензопила HUTER BS-45", brand="HUTER", **kw):
    return Product.objects.create(
        category=leaf, name=name, slug=name.lower().replace(" ", "-") + article.replace("/", "-"),
        brand=brand, article=article, status=ProductStatus.PUBLISHED, is_active=True, **kw,
    )


def write_export(tmp_path, cards):
    path = tmp_path / "products.json"
    path.write_text(json.dumps({"schema_version": 1, "source": "huter",
                                "products": cards}, ensure_ascii=False),
                    encoding="utf-8")
    return path


def card(sku, *, name="Бензопила Huter BS-45", images=("https://huter.su/a.png",),
         attributes=None):
    return {
        "source_url": "https://huter.su/benzopila-huter-bs-45/",
        "name": name,
        "brand": "Huter",
        "manufacturer_sku": sku,
        "attributes": attributes or {"Мощность, кВт": "2,3"},
        "images": [{"url": u, "is_main": i == 0, "alt": None}
                   for i, u in enumerate(images)],
    }


def run(export, **opts):
    call_command("catalog_images_import_scraped", "--export", str(export),
                 "--source", "huter", **opts)


# --------------------------------------------------------------------------- #
# dry-run по умолчанию
# --------------------------------------------------------------------------- #

def test_dry_run_writes_nothing(tmp_path, leaf):
    make_product(leaf, article="70/6/2")
    run(write_export(tmp_path, [card("70/6/2")]))
    assert ProductImage.objects.count() == 0, "без --apply в БД не должно появиться ничего"


def test_dry_run_reports_the_match(tmp_path, leaf, capsys):
    p = make_product(leaf, article="70/6/2")
    run(write_export(tmp_path, [card("70/6/2")]))
    out = capsys.readouterr().out
    assert "70/6/2" in out
    assert str(p.id) in out


# --------------------------------------------------------------------------- #
# Матчинг: только полное совпадение
# --------------------------------------------------------------------------- #

def test_matches_by_exact_article(tmp_path, leaf):
    p = make_product(leaf, article="70/6/2")
    result = _plan(tmp_path, leaf, [card("70/6/2")])
    assert [m["product_id"] for m in result["matched"]] == [p.id]


def test_substring_article_is_not_a_match(tmp_path, leaf):
    """`70/6/2` не должен совпасть с `70/6/25` — это разные товары."""
    make_product(leaf, article="70/6/25")
    result = _plan(tmp_path, leaf, [card("70/6/2")])
    assert result["matched"] == []
    assert result["unmatched_cards"] == 1


def test_our_packaging_suffix_is_stripped(tmp_path, leaf):
    """`_z01` — наш внутренний суффикс фасовки, у производителя его нет."""
    p = make_product(leaf, article="41189-z01")
    result = _plan(tmp_path, leaf, [card("41189")])
    assert [m["product_id"] for m in result["matched"]] == [p.id]


def test_case_and_spaces_ignored(tmp_path, leaf):
    p = make_product(leaf, article="ST7-12-2")
    result = _plan(tmp_path, leaf, [card(" st7-12-2 ")])
    assert [m["product_id"] for m in result["matched"]] == [p.id]


def test_ambiguous_article_is_refused(tmp_path, leaf):
    """Два наших товара с одним артикулом — карточку не привязываем ни к одному."""
    make_product(leaf, article="70/6/2", name="Бензопила А")
    make_product(leaf, article="70/6/2", name="Бензопила Б")
    result = _plan(tmp_path, leaf, [card("70/6/2")])
    assert result["matched"] == []
    assert result["ambiguous"] == 1


# --------------------------------------------------------------------------- #
# Границы
# --------------------------------------------------------------------------- #

def test_manual_source_refused(tmp_path, leaf):
    make_product(leaf, article="70/6/2")
    export = write_export(tmp_path, [card("70/6/2")])
    with pytest.raises(Exception) as exc:
        call_command("catalog_images_import_scraped", "--export", str(export),
                     "--source", "manual")
    assert "manual" in str(exc.value).lower()


def test_content_locked_product_skipped(tmp_path, leaf):
    make_product(leaf, article="70/6/2", content_locked=True)
    result = _plan(tmp_path, leaf, [card("70/6/2")])
    assert result["matched"] == []
    assert result["locked"] == 1


def test_product_with_images_skipped_by_default(tmp_path, leaf):
    p = make_product(leaf, article="70/6/2")
    ProductImage.objects.create(product=p, source=ImageSource.MANUAL,
                                source_url="https://example.com/x.png")
    result = _plan(tmp_path, leaf, [card("70/6/2")])
    assert result["matched"] == []
    assert result["already_has_images"] == 1


def test_card_without_images_is_not_a_candidate(tmp_path, leaf):
    make_product(leaf, article="70/6/2")
    result = _plan(tmp_path, leaf, [card("70/6/2", images=())])
    assert result["matched"] == []
    assert result["cards_without_images"] == 1


# --------------------------------------------------------------------------- #
# Помощник: прогон с машиночитаемым отчётом
# --------------------------------------------------------------------------- #

def _plan(tmp_path, leaf, cards):
    export = write_export(tmp_path, cards)
    out = tmp_path / "plan.json"
    call_command("catalog_images_import_scraped", "--export", str(export),
                 "--source", "huter", "--out", str(out))
    return json.loads(out.read_text(encoding="utf-8"))


def test_packaging_suffix_with_underscore_also_stripped(tmp_path, leaf):
    """В каталоге встречаются обе формы: `41189-z01` и `27361-10_z01`."""
    p = make_product(leaf, article="27361-10_z01")
    result = _plan(tmp_path, leaf, [card("27361-10")])
    assert [m["product_id"] for m in result["matched"]] == [p.id]


def test_article_ending_in_z_digits_without_separator_kept(tmp_path, leaf):
    """`ZP280` не должен пострадать: снимаем только явный суффикс с разделителем."""
    from apps.catalog.management.commands.catalog_images_import_scraped import (
        normalize_article,
    )
    assert normalize_article("ZP280") == "zp280"
    assert normalize_article("41189-z01") == "41189"
    # разделители внутри артикула сохраняются: см. test_normalize_keeps_separators
    assert normalize_article("27361-10_z01") == "27361-10"


# --------------------------------------------------------------------------- #
# Регрессия: разделители в артикуле снимать нельзя
# --------------------------------------------------------------------------- #

def test_separators_are_significant_in_article(tmp_path, leaf):
    """`70/13/3` и `70/1/33` — РАЗНЫЕ артикулы и совпадать не должны.

    Боевой прогон 02.09.2026: первая редакция сносила разделители, оба артикула
    схлопывались в `70133`, и буру AG-150 записалась фотография аккумуляторного
    триммера GET-28Li. Пострадали четыре товара, прогон откатан целиком.
    """
    p = make_product(leaf, article="70/13/3", name="Бур HUTER AG-150")
    result = _plan(tmp_path, leaf, [card("70/1/33", name="Аккумуляторный триммер GET-28Li")])
    assert result["matched"] == [], "чужая карточка не должна была совпасть"
    assert result["unmatched_cards"] == 1
    # а свой артикул по-прежнему находится
    result2 = _plan(tmp_path, leaf, [card("70/13/3")])
    assert [m["product_id"] for m in result2["matched"]] == [p.id]


def test_normalize_keeps_separators():
    from apps.catalog.management.commands.catalog_images_import_scraped import (
        normalize_article,
    )
    assert normalize_article("70/13/3") == "70/13/3"
    assert normalize_article("70/1/33") == "70/1/33"
    assert normalize_article("70/13/3") != normalize_article("70/1/33")
    # регистр и пробелы по-прежнему не значимы
    assert normalize_article(" ST7-12-2 ") == "st7-12-2"


def test_one_product_cannot_take_two_cards(tmp_path, leaf):
    """Две карточки на один товар — отказ: какая из них верная, решает куратор.

    Именно так проявился дефект склейки: товар оказывался в плане дважды и
    получал два разных фото.
    """
    make_product(leaf, article="70/13/3", name="Бур HUTER AG-150")
    result = _plan(tmp_path, leaf, [
        card("70/13/3", images=("https://huter.su/a.png",)),
        card("70/13/3", images=("https://huter.su/b.png",)),
    ])
    assert result["matched"] == []
    assert result["duplicate_cards"] == 1
