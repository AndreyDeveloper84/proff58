"""Генератор кандидатов на правила характеристик (``discover_missing_rules``).

Главное, что проверяем — команда **не может соврать оператору**:

* она ничего не пишет в БД (её единственное безусловное свойство: её гоняют на
  живом стенде);
* частоты шаблонов и ложные срабатывания считаются по фактическим названиям;
* разнородный корпус помечается по признаку, а не по списку slug'ов;
* score получается ровно перемножением пяти множителей из самого отчёта;
* пустой скоуп не падает, а честно говорит, что смотреть нечего.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)
from apps.catalog.rule_discovery import corpus_heterogeneity, scan_names

pytestmark = pytest.mark.django_db

RULES = {
    "version": 1,
    "source_priority": {"manual": 100, "regex": 40},
    "tool_types": [
        {
            "tool_type": "molotki",
            "category": "Ручной инструмент",
            "attributes": [
                {
                    "slug": "weight",
                    "name": "Вес",
                    "kind": "number",
                    "unit": "кг",
                    "source": "regex",
                    "priority": 40,
                    "regex": [r"(\d+(?:[.,]\d+)?)\s*кг"],
                }
            ],
        }
    ],
}


@pytest.fixture()
def rules_dir(tmp_path):
    (tmp_path / "attribute_rules.json").write_text(
        json.dumps(RULES, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture()
def tool_type_attr():
    return Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )


@pytest.fixture()
def live_category():
    root = Category.add_root(name="Инструмент", slug="instrument", is_active=True, on_site=True)
    return root


def make_product(code: str, name: str, category: Category | None = None, **kwargs) -> Product:
    return Product.objects.create(
        code_1c=code,
        name=name,
        original_name=name,
        slug=f"p-{code}",
        status=ProductStatus.PUBLISHED,
        is_active=kwargs.pop("is_active", True),
        available_quantity=kwargs.pop("available_quantity", Decimal("5")),
        category=category,
        **kwargs,
    )


def set_tool_type(product: Product, attr: Attribute, slug: str) -> None:
    option, _ = AttributeOption.objects.get_or_create(
        attribute=attr, slug=slug, defaults={"value": slug}
    )
    ProductAttributeValue.objects.create(
        product=product, attribute=attr, value_option=option, source=Source.MANUAL
    )


def run(rules_dir, **kwargs) -> dict:
    """Прогнать команду и вернуть JSON-отчёт."""
    report_path = rules_dir / "report.json"
    call_command(
        "discover_missing_rules",
        path=str(rules_dir),
        json_report=str(report_path),
        **kwargs,
    )
    return json.loads(report_path.read_text(encoding="utf-8"))


def candidate(report: dict, slug: str) -> dict:
    return next(row for row in report["candidates"] if row["tool_type"] == slug)


# --------------------------------------------------------------------- #
# Главный инвариант: read-only
# --------------------------------------------------------------------- #


def test_command_writes_nothing(rules_dir, tool_type_attr, live_category):
    """Ни одна таблица каталога не меняется — это главное свойство команды."""
    for index in range(8):
        product = make_product(f"w{index}", f"Отвертка {index * 2} мм PH2", live_category)
        set_tool_type(product, tool_type_attr, "otvertki")

    def snapshot() -> tuple:
        return (
            Product.objects.count(),
            ProductAttributeValue.objects.count(),
            Attribute.objects.count(),
            AttributeOption.objects.count(),
            Category.objects.count(),
            CategoryAttribute.objects.count(),
            sorted(Product.objects.values_list("pk", "name", "attrs_cache")),
            sorted(
                ProductAttributeValue.objects.values_list(
                    "pk", "product_id", "attribute_id", "value_option_id", "source"
                )
            ),
        )

    before = snapshot()
    run(rules_dir, in_stock_only=True, active_only=True)
    assert snapshot() == before


# --------------------------------------------------------------------- #
# Частоты и ложные срабатывания
# --------------------------------------------------------------------- #


def test_pattern_frequencies_counted_from_names(rules_dir, tool_type_attr, live_category):
    names = [
        "Ключ гаечный 10х11 мм",
        "Ключ гаечный 12х13 мм",
        "Ключ гаечный 14х15 мм",
        "Ключ гаечный 17х19 мм",
        "Ключ гаечный разводной",
        "Ключ гаечный трещоточный",
    ]
    for index, name in enumerate(names):
        product = make_product(f"k{index}", name, live_category)
        set_tool_type(product, tool_type_attr, "klyuchi-gaechnye")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "klyuchi-gaechnye")
    assert row["products"] == 6

    patterns = {p["pattern"]: p for p in row["patterns"]}
    assert patterns["size_pair"]["hits"] == 4
    assert patterns["size_pair"]["share"] == pytest.approx(4 / 6, abs=1e-4)
    assert patterns["mm"]["hits"] == 4


def test_naive_metre_regex_false_positives_are_reported():
    """Наивный «N м» съедает «16 мм» и «2 мАч» — команда обязана это показать.

    Именно этот класс ошибки даёт на стенде 188 ложных срабатываний у свёрл:
    «ф 3,2 мм» читается как «3,2 метра». Регулярку крутящего момента («350Нм»)
    наивная метровая версия при этом НЕ ловит — после числа идёт «Н», а не «м»;
    здесь зафиксировано и это, чтобы отчёт не приписывал себе чужих ошибок.
    """
    names = [
        "Сверло 16 мм",
        "Аккумулятор 2 мАч",
        "Рулетка 5 м",
        'Головка торцевая 350Нм 1/2"',
    ]
    hits = scan_names(names)["m"]
    assert hits.naive_hits == 3
    # Защищённая регулярка оставляет только настоящие метры.
    assert hits.guarded_hits == 1
    assert hits.false_positives == 2
    assert any("16 мм" in example for example in hits.false_positive_examples)


def test_noisy_pattern_is_rejected_not_proposed(rules_dir, tool_type_attr, live_category):
    """Шаблон, ошибающийся чаще порога, не предлагается, но и не прячется.

    Корпус подобран так, что шаблон одновременно частый (проходит порог доли) и
    шумный: 6 настоящих метров и 4 «мм», которые наивная регулярка читает как
    метры. Без гейта такой шаблон попал бы в рекомендации как полноценный.
    """
    for index in range(6):
        product = make_product(f"n{index}", f"Рулетка измерительная {index + 3} м", live_category)
        set_tool_type(product, tool_type_attr, "izm-ruletki-test")
    for index in range(4):
        product = make_product(f"nf{index}", f"Рулетка полотно {index + 16} мм", live_category)
        set_tool_type(product, tool_type_attr, "izm-ruletki-test")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "izm-ruletki-test")
    metre = next(p for p in row["patterns"] if p["pattern"] == "m")
    assert metre["naive_hits"] == 10
    assert metre["hits"] == 6
    assert metre["false_positives"] == 4
    assert metre["share"] == pytest.approx(0.6)
    assert metre["false_positive_rate"] == pytest.approx(0.4)
    assert metre["proposed"] is False
    assert "шум" in metre["rejected_reason"]
    assert "length" not in row["proposed_attributes"]

    # С поднятым порогом тот же шаблон предлагается — гейт управляем, а не зашит.
    relaxed = candidate(
        run(rules_dir, in_stock_only=True, max_false_positive_rate=0.5), "izm-ruletki-test"
    )
    relaxed_metre = next(p for p in relaxed["patterns"] if p["pattern"] == "m")
    assert relaxed_metre["proposed"] is True
    assert relaxed_metre["rejected_reason"] == ""


# --------------------------------------------------------------------- #
# Разнородный корпус
# --------------------------------------------------------------------- #


def test_heterogeneous_corpus_is_flagged_by_signal(rules_dir, tool_type_attr, live_category):
    """«Свалка» ловится по расхождению ведущих слов, а не по списку slug'ов."""
    names = [
        "Струбцина 100 мм",
        "Переходник 20 мм",
        "Заклёпка 4 мм",
        "Крючок 30 мм",
        "Пружина 15 мм",
        "Ролик 25 мм",
        "Втулка 12 мм",
        "Шпилька 8 мм",
        "Планка 40 мм",
        "Скоба 16 мм",
        "Зажим 22 мм",
        "Держатель 35 мм",
        "Кольцо 18 мм",
        "Прокладка 14 мм",
        "Хомут 28 мм",
        "Клипса 9 мм",
        "Направляющая 55 мм",
        "Ограничитель 60 мм",
        "Фиксатор 11 мм",
        "Упор 13 мм",
        "Подпятник 19 мм",
    ]
    for index, name in enumerate(names):
        product = make_product(f"h{index}", name, live_category)
        set_tool_type(product, tool_type_attr, "prochaya-osnastka")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "prochaya-osnastka")
    assert row["status"] == "BLOCKED_BY_CLASSIFICATION"
    assert row["heterogeneity"]["flagged"] is True
    assert "разбор на подтипы" in row["reason"]


def test_homogeneous_corpus_is_not_flagged(rules_dir, tool_type_attr, live_category):
    """Однородный тип того же размера разнородным НЕ считается."""
    for index in range(21):
        product = make_product(f"u{index}", f"Молоток слесарный {index + 1} кг", live_category)
        set_tool_type(product, tool_type_attr, "molotki-slesarnye")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "molotki-slesarnye")
    assert row["heterogeneity"]["flagged"] is False
    assert row["status"] != "BLOCKED_BY_CLASSIFICATION"


def test_head_token_and_heterogeneity_are_pure():
    hetero = corpus_heterogeneity(["Молоток 1 кг", "Молоток 2 кг", "Кувалда 5 кг"])
    assert hetero.total == 3
    assert hetero.distinct_heads == 2
    assert hetero.top_head == "молоток"
    assert hetero.dominance == pytest.approx(2 / 3)


# --------------------------------------------------------------------- #
# Наборы
# --------------------------------------------------------------------- #


def test_set_type_is_skipped_and_uses_piece_count(rules_dir, tool_type_attr, live_category):
    for index in range(8):
        product = make_product(f"s{index}", f"Набор бит {index + 4} шт", live_category)
        set_tool_type(product, tool_type_attr, "nabory-bit")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "nabory-bit")
    assert row["status"] == "SKIP_SET"
    assert row["is_set_type"] is True
    # «N шт» у набора — это число предметов, а не фасовка.
    pcs = next(p for p in row["patterns"] if p["pattern"] == "pcs")
    assert pcs["attribute_slug"] == "piece_count"


def test_single_set_product_does_not_mark_whole_type(rules_dir, tool_type_attr, live_category):
    """Один «Набор головок» внутри обычного типа не делает набором весь тип."""
    names = [f"Головка торцевая {index + 8} мм" for index in range(9)]
    names.append("Набор головок 10 шт")
    for index, name in enumerate(names):
        product = make_product(f"g{index}", name, live_category)
        set_tool_type(product, tool_type_attr, "golovki")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "golovki")
    assert row["is_set_type"] is False
    assert row["status"] != "SKIP_SET"


# --------------------------------------------------------------------- #
# Rule Impact Score
# --------------------------------------------------------------------- #


def test_score_equals_product_of_five_factors(rules_dir, tool_type_attr, live_category):
    for index in range(12):
        product = make_product(f"r{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "krep-styazhki")
    factors = row["score_factors"]
    expected = (
        factors["products"]
        * factors["attributes"]
        * factors["sales_weight"]
        * factors["extraction_confidence"]
        * factors["facet_visibility"]
    )
    assert row["score"] == pytest.approx(round(expected, 2), abs=0.02)
    assert factors["products"] == 12


def test_sales_weight_degrades_explicitly_without_sales(rules_dir, tool_type_attr, live_category):
    """Нет продаж — вес нейтрализуется в 1.0 и об этом сказано, а не ноль."""
    for index in range(10):
        product = make_product(f"q{index}", f"Хомут {index + 5} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    report = run(rules_dir, in_stock_only=True)
    assert report["sales"]["data_absent"] is True
    assert report["sales"]["products_with_sales_in_scope"] == 0
    assert "НЕ участвует" in report["sales"]["degradation"]
    assert candidate(report, "krep-styazhki")["score_factors"]["sales_weight"] == 1.0
    # Деградация не обнуляет рейтинг.
    assert candidate(report, "krep-styazhki")["score"] > 0


def test_dead_category_blocks_and_zeroes_facet_visibility(rules_dir, tool_type_attr):
    dead = Category.add_root(name="Мёртвая", slug="dead", is_active=False, on_site=False)
    for index in range(10):
        product = make_product(f"d{index}", f"Хомут-стяжка {index + 3} мм 50 шт", dead)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "krep-styazhki")
    assert row["score_factors"]["facet_visibility"] == 0.0
    assert row["status"] == "BLOCKED_BY_CATEGORY"
    assert row["score"] == 0.0


def test_missing_attribute_blocks_the_type(rules_dir, tool_type_attr, live_category):
    for index in range(10):
        product = make_product(f"m{index}", f"Наждачка P{40 + index * 10} 100 мм", live_category)
        set_tool_type(product, tool_type_attr, "nazhdachka")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "nazhdachka")
    assert row["status"] == "BLOCKED_BY_ATTRIBUTE"
    assert "grit" in row["missing_attributes"]

    # Заводим атрибуты — блокер снимается.
    for slug, name in (("grit", "Зернистость"), ("diameter", "Диаметр")):
        Attribute.objects.create(slug=slug, name=name, attribute_type=AttributeType.DECIMAL)
    report = run(rules_dir, in_stock_only=True)
    assert candidate(report, "nazhdachka")["status"] == "CREATE_RULE"


# --------------------------------------------------------------------- #
# Хвост, скоуп и отчёт
# --------------------------------------------------------------------- #


def test_long_tail_is_aggregated_not_proposed(rules_dir, tool_type_attr, live_category):
    for index in range(3):
        product = make_product(f"t{index}", f"Редкий инструмент {index} 10 мм", live_category)
        set_tool_type(product, tool_type_attr, f"redkiy-{index}")

    report = run(rules_dir, in_stock_only=True, tail_threshold=6)
    assert report["totals"]["tail_types"] == 3
    assert report["totals"]["tail_products"] == 3
    assert {row["status"] for row in report["candidates"]} == {"TAIL_GENERIC"}


def test_scope_filters_intersect(rules_dir, tool_type_attr, live_category):
    in_stock = make_product("f1", "Хомут-стяжка 10 мм 50 шт", live_category)
    set_tool_type(in_stock, tool_type_attr, "krep-styazhki")
    out_of_stock = make_product(
        "f2", "Хомут-стяжка 12 мм 50 шт", live_category, available_quantity=Decimal("0")
    )
    set_tool_type(out_of_stock, tool_type_attr, "krep-styazhki")
    inactive = make_product("f3", "Хомут-стяжка 14 мм 50 шт", live_category, is_active=False)
    set_tool_type(inactive, tool_type_attr, "krep-styazhki")

    assert run(rules_dir)["totals"]["products"] == 3
    assert run(rules_dir, in_stock_only=True)["totals"]["products"] == 2
    assert run(rules_dir, in_stock_only=True, active_only=True)["totals"]["products"] == 1
    assert run(rules_dir, tool_type=["nabory-bit"])["totals"]["products"] == 0


def test_json_report_is_valid_and_self_describing(rules_dir, tool_type_attr, live_category):
    product = make_product("j1", "Хомут-стяжка 10 мм 50 шт", live_category)
    set_tool_type(product, tool_type_attr, "krep-styazhki")

    report = run(rules_dir, in_stock_only=True, min_pattern_share=0.2)
    assert report["scope"]["read_only"] is True
    # Все пороги, влияющие на числа, зафиксированы в отчёте — иначе он невоспроизводим.
    assert report["scope"]["min_pattern_share"] == 0.2
    assert report["scope"]["tail_threshold"] == 6
    assert report["scope"]["sales_min_share"] == 0.01
    assert report["scope"]["max_false_positive_rate"] == 0.33
    assert set(report) == {
        "scope",
        "totals",
        "sales",
        "candidates",
        "cumulative_by_volume",
    }
    assert set(report["cumulative_by_volume"]) == {"all", "gap"}
    # Отчёт обязан пережить сериализацию без потерь.
    assert json.loads(json.dumps(report, ensure_ascii=False)) == report


def test_empty_scope_does_not_crash(rules_dir, tool_type_attr):
    report = run(rules_dir, in_stock_only=True)
    assert report["totals"]["products"] == 0
    assert report["candidates"] == []
    assert report["cumulative_by_volume"]["gap"]["types"] == 0


def test_untyped_products_counted_as_blockless(rules_dir, live_category):
    """Товар без tool_type — тоже «тип без блока»: правил для него не существует."""
    make_product("x1", "Неопознанный предмет 10 мм", live_category)

    report = run(rules_dir, in_stock_only=True)
    assert report["totals"]["untyped"] == 1
    assert report["totals"]["without_attributes_no_block"] == 1


def test_faceted_category_raises_visibility(rules_dir, tool_type_attr, live_category):
    attribute = Attribute.objects.create(
        slug="diameter", name="Диаметр", attribute_type=AttributeType.DECIMAL
    )
    for index in range(10):
        product = make_product(f"v{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    without_binding = candidate(run(rules_dir, in_stock_only=True), "krep-styazhki")
    assert without_binding["score_factors"]["facet_visibility"] == pytest.approx(0.75)

    CategoryAttribute.objects.create(category=live_category, attribute=attribute, is_filter=True)
    with_binding = candidate(run(rules_dir, in_stock_only=True), "krep-styazhki")
    assert with_binding["score_factors"]["facet_visibility"] == pytest.approx(1.0)
    assert with_binding["score"] > without_binding["score"]
