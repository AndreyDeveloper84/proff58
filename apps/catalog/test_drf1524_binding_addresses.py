"""ДРФ-1524: адреса привязок фасетов и явный отказ от фасета.

Волна ДРФ-1450 записала значения, но привязки к листьям не создались: покупатель
осей не видит. План штатной команды показывал 20 несозданных привязок — 8 «ниже
порога» и 12 «не резолвятся».

**Замер по листьям вместо разделов перевернул картину.** Низкое покрытие было не
свойством оси, а следствием слишком широкого адреса: блок объявлял раздел, а
значения писались по узкому ``tool_type``.

| было объявлено | покрытие | фактический лист | покрытие |
|---|---|---|---|
| 365 Хомуты и стяжки, 4 оси | 36–38 % | 426 Хомуты обжимные · 427 Хомуты-стяжки | 86–96 % |
| 418 Зубила, кернеры и бородки, `diameter` | 22 % | 429 Кернеры и бородки | 78 % |
| «Ленты шлифовальные» — узла нет | — | 102 Абразивы | 74–82 % |
| «Наждачная бумага и сетка» — узла нет | — | 102 Абразивы | 74–82 % |
| «Ящики, сумки и органайзеры» — узла нет | — | 214 Ящики для инструмента | 62 % |
| «Стамески и долота» — узла нет | — | 419 Стамески, долота и резцы | 83 % |
| «Развёртки, зенкеры и фрезы» — узла нет | — | 425 Фрезы | 86 % |

Проверяемые границы:

1. **``bind: false`` — явный отказ от фасета.** Без флага вариант «оставить без
   фасета» выразить в словаре нечем: ось вечно висит в плане как несозданная, и
   «решили не делать» неотличимо от «забыли». Именно поэтому проверку привязок
   нельзя было сделать фатальной.
2. **Оси одного блока живут в разных листьях.** У ``krep-styazhki`` диаметры
   шланга принадлежат обжимным хомутам, длина и ширина — стяжкам.
3. **Ни одно имя категории в словаре не должно быть выдуманным.** Прежние шесть
   не существовали в дереве ни в каком виде, а команда пропускала их молча.
4. **Граница «мм» у изоленты пропускает разделитель размера.** «15ммх10м»
   написано слитно, и прежнее ``(?![а-яa-z])`` отвергало ширину из-за «х».
"""

from __future__ import annotations

import json
import re

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir


@pytest.fixture(scope="module")
def blocks() -> dict:
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    return {b["tool_type"]: b for b in data["tool_types"]}


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _axis(blocks: dict, tool_type: str, slug: str) -> dict:
    return next(a for a in blocks[tool_type]["attributes"] if a["slug"] == slug)


@pytest.mark.parametrize(
    "tool_type,expected",
    [
        ("lenty-shlif", "Абразивы"),
        ("nazhdachka", "Абразивы"),
        ("yashchiki-sumki", "Ящики для инструмента"),
        ("stameski", "Стамески, долота и резцы по дереву"),
        ("krep-takelazh", "Тросы, стяжки и стропы"),
        ("razvertki-frezy", "Фрезы"),
    ],
)
def test_invented_category_names_replaced_with_live_leaves(blocks, tool_type, expected):
    """Шесть имён не существовали в дереве — команда пропускала блок молча."""
    assert blocks[tool_type]["category"] == expected


def test_axes_of_one_block_may_live_in_different_leaves(blocks):
    """У хомутов диаметры шланга и габариты стяжки — разные листья.

    Общий адрес «Хомуты и стяжки» (365, 155 товаров) разбавлял все четыре оси до
    36–38 % и показывал их непроходными, хотя на своих листьях они берут 86–96 %.
    """
    assert "category" not in blocks["krep-styazhki"], "блочного адреса быть не должно"
    for slug in ("hose_diameter_from", "hose_diameter_to"):
        assert _axis(blocks, "krep-styazhki", slug)["category"] == "Хомуты обжимные"
    for slug in ("length", "width"):
        assert _axis(blocks, "krep-styazhki", slug)["category"] == "Хомуты-стяжки"


def test_chisel_diameter_points_at_the_punch_leaf(blocks):
    """У зубил диаметра нет вовсе — ось принадлежит кернерам и бородкам."""
    assert _axis(blocks, "zubila", "diameter")["category"] == "Кернеры и бородки"
    for slug in ("width", "length"):
        assert "category" not in _axis(blocks, "zubila", slug)


def test_no_facet_is_written_down_not_left_dangling(blocks):
    """Развилка В выражается флагом, а не молчанием.

    У ножей длина берёт 21 % по чистому типу, ширина 42 %, более узкого листа
    нет, и 25 названий из 76 вообще не несут размера. Фасета не будет — и это
    записано, чтобы план перестал показывать две вечно несозданные привязки.
    """
    for slug in ("width", "length"):
        assert _axis(blocks, "nozhi", slug)["bind"] is False
    assert "bind" not in _axis(blocks, "nozhi", "knife_type")
    assert _axis(blocks, "hoz-izolenta", "tape_width")["bind"] is False


def test_tape_width_boundary_allows_a_size_separator(blocks):
    """«15ммх10м» написано слитно: после «мм» идёт «х», а не пробел.

    Прежняя граница отвергала такую ширину. Замер: было 35 из 46 (76 %),
    стало 43 (93 %).
    """
    pattern = _axis(blocks, "hoz-izolenta", "tape_width")["regex"][0]
    rx = re.compile(pattern)
    for name, expected in (
        ("изолента 15ммх10м белая сибртех", "15"),
        ("изолента пвх 15ммх20м белая", "15"),
        ("изолента 19ммх20м черная fit", "19"),
        ("изолента пвх 19мм х 20м синяя зубр", "19"),
        ("изолента пвх синяя 15 мм*20 м hobbi", "15"),
        ("изолента х/б, ширина 18мм, 15м, 1000 в, черная", "18"),
    ):
        m = rx.search(name)
        assert m and m.group(1) == expected, name

    # Ленты, которые продаются на вес, ширины не несут — честный ноль.
    for name in ("изолента х/б прорезиненная черная 110г (114)", "изолента хб черная, 70г."):
        assert rx.search(name) is None, name


def test_every_declared_category_name_is_a_string_or_absent(blocks):
    """Регресс-страховка: адрес — либо непустая строка, либо его нет.

    Пустая строка провалилась бы в блочный адрес незаметно.
    """
    for tool_type, block in blocks.items():
        if "category" in block:
            assert isinstance(block["category"], str) and block["category"].strip(), tool_type
        for a in block["attributes"]:
            if "category" in a:
                assert (
                    isinstance(a["category"], str) and a["category"].strip()
                ), f"{tool_type}/{a['slug']}"
            if "bind" in a:
                assert a["bind"] is False, f"{tool_type}/{a['slug']}: bind бывает только false"


def test_rules_still_load(rules):
    """Правки адресов не должны ломать загрузку словаря."""
    assert rules.rules_for("krep-styazhki")
    assert rules.rules_for("nozhi")
    assert rules.rules_for("hoz-izolenta")
