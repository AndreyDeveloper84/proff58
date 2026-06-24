"""Тесты чистой логики аудита таксономии (``apps.catalog.taxonomy_audit``).

БД не требуется — проверяем подсчёты объёмов и срабатывание находок на
синтетическом мини-дереве 1С.
"""

from __future__ import annotations

from apps.catalog.taxonomy_audit import analyze


def _product(ext, name, sg=""):
    return {"ProductGroup": "0", "external_id": ext, "name": name, "source_group": sg}


def _group(ext, name, children):
    return {"ProductGroup": "1", "external_id": ext, "name": name, "children": children}


def _build_tree():
    # Электроинструмент: деление по питанию (F1) — две группы по 1 товару.
    setevoy = _group("g-set", "Сетевой", [_product("p1", "Перфоратор сетевой")])
    akkum = _group("g-akk", "Аккумуляторный", [_product("p2", "Дрель аккумуляторная")])
    # Узел-бренд (F4) + дубль с tool_type «Коронки» (F5).
    zap = _group("g-zap", "Запчасти Hitachi", [_product("p3", "Щётка")])
    koronki = _group("g-kor", "Коронки", [_product("p4", "Коронка 68")])
    # Off_site грязь.
    musor = _group("g-mus", "яяПриход", [_product("p5", "Хлам")])
    return [setevoy, akkum, zap, koronki, musor]


def _mapping():
    return [
        {
            "external_id": "g-set",
            "group_1c": "Сетевой",
            "site_path": ["Электроинструмент", "Сетевой инструмент"],
            "on_site": True,
        },
        {
            "external_id": "g-akk",
            "group_1c": "Аккумуляторный",
            "site_path": ["Электроинструмент", "Аккумуляторный инструмент"],
            "on_site": True,
        },
        {
            "external_id": "g-zap",
            "group_1c": "Запчасти Hitachi",
            "site_path": ["Запчасти", "Запчасти Hitachi"],
            "on_site": True,
        },
        {
            "external_id": "g-kor",
            "group_1c": "Коронки",
            "site_path": ["Оснастка и расходники", "Коронки"],
            "on_site": True,
        },
        {"external_id": "g-mus", "group_1c": "яяПриход", "site_path": [], "on_site": False},
    ]


def _tt_rules():
    return {
        "categories": [
            {
                "category": "Оснастка и расходники",
                "extraction": "inherit_1c_subgroup",
                "rules": [{"tool_type": "Коронки", "slug": "koronki"}],
            }
        ]
    }


def _attr_rules():
    return {
        "tool_types": [
            {
                "tool_type": "koronki",
                "category": "Оснастка и расходники",
                "attributes": [{"slug": "diameter", "kind": "number", "is_filter": True}],
            }
        ]
    }


def test_counts_mapped_offsite_unmapped():
    r = analyze(_mapping(), _build_tree(), _tt_rules(), _attr_rules())
    # 5 товаров: 4 on_site + 1 off_site, 0 без маппинга.
    assert r.total_products == 5
    assert r.mapped_onsite == 4
    assert r.offsite == 1
    assert r.unmapped == 0


def test_unmapped_group_goes_to_neразобранные():
    # Группа без записи в mapping → товар считается «без маппинга».
    tree = [_group("g-x", "Неизвестная", [_product("p9", "Нечто")])]
    r = analyze([], tree, {}, {"tool_types": []})
    assert r.unmapped == 1
    assert r.mapped_onsite == 0


def test_finding_power_split_F1():
    r = analyze(_mapping(), _build_tree(), _tt_rules(), _attr_rules())
    f1 = {f.code: f for f in r.findings}.get("F1")
    assert f1 is not None and f1.severity == "high"
    leaves = {row[0] for row in f1.rows}
    assert "Электроинструмент / Сетевой инструмент" in leaves
    assert "Электроинструмент / Аккумуляторный инструмент" in leaves


def test_finding_brand_node_F4():
    r = analyze(_mapping(), _build_tree(), _tt_rules(), _attr_rules())
    f4 = {f.code: f for f in r.findings}.get("F4")
    assert f4 is not None
    assert any("Hitachi" in row[0] for row in f4.rows)


def test_finding_dup_axis_F5_exact_only():
    r = analyze(_mapping(), _build_tree(), _tt_rules(), _attr_rules())
    f5 = {f.code: f for f in r.findings}.get("F5")
    assert f5 is not None
    nodes = {row[0] for row in f5.rows}
    # «Коронки» — точное совпадение листа и значения tool_type.
    assert "Оснастка и расходники / Коронки" in nodes
    # Бренд-узел не должен попадать в F5 (это F4, не дубль оси).
    assert all("Hitachi" not in n for n in nodes)


def test_designed_axes_summary():
    r = analyze(_mapping(), _build_tree(), _tt_rules(), _attr_rules())
    axes = r.designed_axes
    assert axes["tool_types_per_category"]["Оснастка и расходники"] == 1
    assert axes["attributes_per_tool_type"]["koronki"]["filter"] == 1
