"""Генератор кандидатов на правила характеристик (``discover_missing_rules``).

Главное, что проверяем — команда **не может соврать оператору**:

* она ничего не пишет в БД (её единственное безусловное свойство: её гоняют на
  живом стенде);
* частоты шаблонов и ложные срабатывания считаются по фактическим названиям;
* разнородный корпус помечается по признаку, а не по списку slug'ов;
* score получается ровно перемножением пяти множителей из самого отчёта;
* пустой скоуп не падает, а честно говорит, что смотреть нечего;
* Markdown-отчёт содержит те же числа и остаётся валидной разметкой — регулярка
  с ``|`` внутри не должна разваливать таблицу.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog.management.commands.discover_missing_rules import resolve_binding_category
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


def run_md(rules_dir, **kwargs) -> str:
    """Прогнать команду и вернуть текст Markdown-отчёта."""
    md_path = rules_dir / "report.md"
    call_command(
        "discover_missing_rules",
        path=str(rules_dir),
        md_report=str(md_path),
        **kwargs,
    )
    return md_path.read_text(encoding="utf-8")


def candidate(report: dict, slug: str) -> dict:
    return next(row for row in report["candidates"] if row["tool_type"] == slug)


_PIPE_RE = re.compile(r"(?<!\\)\|")


def assert_markdown_tables_are_valid(text: str) -> int:
    """Проверить таблицы Markdown: одинаковое число колонок и строка выравнивания.

    Проверяем именно неэкранированные трубы: значение с ``|`` внутри обязано быть
    экранировано, иначе таблица молча разъезжается — а отчёт вставляют в задачу.
    """
    tables = 0
    block: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            block.append(line)
            continue
        if block:
            assert len(block) >= 2, f"таблица без строки выравнивания: {block}"
            columns = len(_PIPE_RE.findall(block[0]))
            assert all(
                set(cell.strip()) <= {"-", ":"} and cell.strip()
                for cell in block[1].strip("|").split("|")
            ), f"вторая строка таблицы не выравнивание: {block[1]}"
            for row in block:
                assert len(_PIPE_RE.findall(row)) == columns, f"колонки разъехались: {row}"
            tables += 1
            block = []
    return tables


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
    assert report["scope"]["min_facet_fill_rate"] == 0.1
    assert set(report) == {
        "scope",
        "totals",
        "sales",
        "candidates",
        "binding_targets",
        "axis_ranking",
        "facet_binding_queue",
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


# --------------------------------------------------------------------- #
# Разбивка по осям: potential / actionable / blocked
# --------------------------------------------------------------------- #


def axis(row: dict, slug: str) -> dict:
    return next(item for item in row["axes"] if item["attribute_slug"] == slug)


def write_rules(tmp_path, blocks) -> object:
    """Свой файл правил с блоками и их полем ``category``.

    Отдельная фикстура, а не общая ``RULES``: поле ``category`` блока — это не
    справка, а адрес, куда ``load_attributes`` поставит привязку. Проверять
    поведение, зависящее от него, на файле без блоков значит проверять презумпцию
    вместо факта.
    """
    (tmp_path / "attribute_rules.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source_priority": {"manual": 100, "regex": 40},
                "tool_types": blocks,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


def block(tool_type: str, category: str) -> dict:
    """Блок правил с одной уже описанной осью, не пересекающейся с шаблонами.

    ``weight`` берётся намеренно: он не мешает шаблонам «N мм» и «N шт»
    предлагать новые оси, но делает блок существующим — а значит цель привязки
    известной.
    """
    return {
        "tool_type": tool_type,
        "category": category,
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


@pytest.fixture()
def hand_tools_tree():
    """Дерево владельца в миниатюре: корень раздела и профильный лист под ним."""
    root = Category.add_root(name="Ручной инструмент", slug="ruchnoy", is_active=True, on_site=True)
    leaf = root.add_child(name="Ключи", slug="klyuchi", is_active=True, on_site=True)
    other_root = Category.add_root(name="Оснастка", slug="osnastka", is_active=True, on_site=True)
    return {"root": root, "leaf": leaf, "other_root": other_root}


def make_wrenches(tool_type_attr: Attribute, category: Category, count: int = 10) -> None:
    for index in range(count):
        product = make_product(f"kg{index}", f"Ключ гаечный {index + 8} мм", category)
        set_tool_type(product, tool_type_attr, "klyuchi-gaechnye")


def make_diameter_attribute() -> Attribute:
    return Attribute.objects.create(
        slug="diameter", name="Диаметр", attribute_type=AttributeType.DECIMAL
    )


# --- лестница разрешения имени категории ------------------------------- #


def test_resolve_binding_category_repeats_load_attributes_ladder(live_category):
    """Живой узел важнее мёртвого, ``depth == 1`` важнее вложенного, иначе — ambiguous."""
    root = Category.add_root(name="Ключи", slug="klyuchi-root", is_active=True, on_site=True)
    root.add_child(name="Ключи", slug="klyuchi-child", is_active=True, on_site=True)
    dead = Category.add_root(name="Мёртвые", slug="mertvye", is_active=False, on_site=False)
    dead.add_child(name="Уникальные", slug="unikalnye", is_active=False, on_site=False)
    twin_root = Category.add_root(name="Дубли", slug="dubli", is_active=True, on_site=True)
    twin_root.add_child(name="Двойник", slug="dvoynik-1", is_active=True, on_site=True)
    twin_root.add_child(name="Двойник", slug="dvoynik-2", is_active=True, on_site=True)

    categories = {
        row["pk"]: row
        for row in Category.objects.values("pk", "name", "path", "depth", "is_active", "on_site")
    }

    # Одноимённые узлы: побеждает верхний уровень.
    category_id, reason = resolve_binding_category("Ключи", categories)
    assert category_id == root.pk
    assert reason == "bound:top"

    # Живых нет вовсе — выбирается мёртвый, но исход помечен отдельно.
    category_id, reason = resolve_binding_category("Уникальные", categories)
    assert reason.endswith(":dead")

    # Два живых одноуровневых кандидата — гадать нельзя.
    assert resolve_binding_category("Двойник", categories) == (None, "ambiguous:tree")
    assert resolve_binding_category("Нет такой", categories) == (None, "not_found")
    assert resolve_binding_category("", categories) == (None, "no_category")


# --- видимость оси считается по цели привязки --------------------------- #


def test_visibility_is_counted_by_block_binding_category(tmp_path, tool_type_attr, hand_tools_tree):
    """Видимость — по категории, куда уйдёт привязка, а не где лежат товары.

    Случай владельца: блок `klyuchi-gaechnye` указывает «Ручной инструмент» —
    корень раздела, — а товары лежат в «Ключах». Корень товары накрывает
    (фасеты наследуются вниз), но фасет ложится на весь раздел.
    """
    make_diameter_attribute()
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Ручной инструмент")])

    row = candidate(run(rules, in_stock_only=True), "klyuchi-gaechnye")
    target = row["binding_target"]
    assert target["category_id"] == hand_tools_tree["root"].pk
    assert target["reason"] == "bound:top"
    assert target["source"] == "block"
    assert target["products_covered"] == 10
    # Товары стоят НЕ в целевой категории — фасет уходит выше, чем нужно.
    assert target["products_at_target"] == 0
    assert axis(row, "diameter")["status"] == "READY"
    assert axis(row, "diameter")["actionable_values"] == 10
    # Привязки ещё нет, значит видимость даёт именно будущая цель.
    assert axis(row, "diameter")["already_visible_values"] == 0
    assert axis(row, "diameter")["unlocked_by_binding_target"] == 10


def test_axis_blocked_when_binding_target_does_not_cover_products(
    tmp_path, tool_type_attr, hand_tools_tree
):
    """Цель привязки не накрывает товары → BLOCKED_BY_FACET и ноль actionable.

    Без этой проверки оценка была бы завышенной: команда посчитала бы привязку к
    категории товара, которой ``load_attributes`` не создаст.
    """
    make_diameter_attribute()
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Оснастка")])

    row = candidate(run(rules, in_stock_only=True), "klyuchi-gaechnye")
    blocked = axis(row, "diameter")
    assert row["binding_target"]["category_id"] == hand_tools_tree["other_root"].pk
    assert row["binding_target"]["products_covered"] == 0
    assert blocked["status"] == "BLOCKED_BY_FACET"
    assert blocked["next_action"] == "FACET_BINDING_AUDIT"
    assert blocked["potential_values"] == 10
    assert blocked["actionable_values"] == 0
    assert blocked["visibility"] == pytest.approx(0.0)
    assert row["actionable_values"] == 0
    assert row["blocked_values"] == row["potential_values"]


def test_dead_binding_target_blocks_axis(tmp_path, tool_type_attr, hand_tools_tree):
    """Мёртвая цель фасета не даёт: живым потомкам от скрытого узла не наследуется."""
    make_diameter_attribute()
    Category.add_root(name="Метчики и плашки", slug="metchiki", is_active=False, on_site=False)
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Метчики и плашки")])

    report = run(rules, in_stock_only=True)
    row = candidate(report, "klyuchi-gaechnye")
    assert row["binding_target"]["reason"].endswith(":dead")
    assert row["binding_target"]["is_live"] is False
    assert axis(row, "diameter")["status"] == "BLOCKED_BY_FACET"
    assert report["binding_targets"]["unresolved"] == 1


def test_ambiguous_binding_target_blocks_axis(tmp_path, tool_type_attr, hand_tools_tree):
    """Неоднозначное имя — привязки не будет вовсе, гадать команда не имеет права."""
    make_diameter_attribute()
    twin = Category.add_root(name="Дубли", slug="dubli", is_active=True, on_site=True)
    twin.add_child(name="Двойник", slug="dvoynik-1", is_active=True, on_site=True)
    twin.add_child(name="Двойник", slug="dvoynik-2", is_active=True, on_site=True)
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Двойник")])

    report = run(rules, in_stock_only=True)
    row = candidate(report, "klyuchi-gaechnye")
    assert row["binding_target"]["category_id"] is None
    assert row["binding_target"]["reason"] == "ambiguous:tree"
    assert axis(row, "diameter")["status"] == "BLOCKED_BY_FACET"
    assert report["binding_targets"]["unresolved"] == 1


def test_existing_binding_counts_even_when_target_is_wrong(
    tmp_path, tool_type_attr, hand_tools_tree
):
    """Уже существующая привязка делает ось видимой независимо от цели блока."""
    attribute = make_diameter_attribute()
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    CategoryAttribute.objects.create(
        category=hand_tools_tree["leaf"], attribute=attribute, is_filter=True
    )
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Оснастка")])

    ready = axis(candidate(run(rules, in_stock_only=True), "klyuchi-gaechnye"), "diameter")
    assert ready["status"] == "READY"
    assert ready["already_visible_values"] == 10
    assert ready["unlocked_by_binding_target"] == 0
    assert ready["actionable_values"] == 10


def test_visibility_counts_existing_binding_on_ancestor(tmp_path, tool_type_attr, hand_tools_tree):
    """Фасеты наследуются вниз: привязка у предка засчитывается товарам листа."""
    attribute = make_diameter_attribute()
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Оснастка")])

    before = axis(candidate(run(rules, in_stock_only=True), "klyuchi-gaechnye"), "diameter")
    assert before["status"] == "BLOCKED_BY_FACET"

    # Привязка стоит у КОРНЯ, товары — в листе.
    CategoryAttribute.objects.create(
        category=hand_tools_tree["root"], attribute=attribute, is_filter=True
    )
    after = axis(candidate(run(rules, in_stock_only=True), "klyuchi-gaechnye"), "diameter")
    assert after["status"] == "READY"
    assert after["already_visible_values"] == 10
    assert after["visibility"] == pytest.approx(1.0)


def test_binding_of_other_attribute_does_not_make_axis_visible(
    tmp_path, tool_type_attr, hand_tools_tree
):
    """Привязан чужой атрибут — ось всё равно невидима.

    Прежняя мерка «у категории есть хоть какой-то фильтр» засчитала бы этот
    случай как видимый: ровно так 74 значения `material` у ключей выглядели
    работоспособными при непривязанном атрибуте.
    """
    make_diameter_attribute()
    alien = Attribute.objects.create(
        slug="voltage", name="Напряжение", attribute_type=AttributeType.DECIMAL
    )
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    CategoryAttribute.objects.create(
        category=hand_tools_tree["leaf"], attribute=alien, is_filter=True
    )
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Оснастка")])

    row = candidate(run(rules, in_stock_only=True), "klyuchi-gaechnye")
    assert axis(row, "diameter")["status"] == "BLOCKED_BY_FACET"
    assert row["actionable_values"] == 0
    # А тип-уровневая facet_visibility «какой-то фильтр есть» — 1.0.
    assert row["score_factors"]["facet_visibility"] == pytest.approx(1.0)


def test_axis_without_attribute_in_db_is_blocked_by_attribute(
    rules_dir, tool_type_attr, live_category
):
    """Атрибута нет в БД → BLOCKED_BY_ATTRIBUTE, лечение — load_attributes."""
    for index in range(10):
        product = make_product(f"na{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    row = candidate(run(rules_dir, in_stock_only=True), "krep-styazhki")
    blocked = axis(row, "diameter")
    assert blocked["status"] == "BLOCKED_BY_ATTRIBUTE"
    assert blocked["next_action"] == "LOAD_ATTRIBUTES"
    assert blocked["potential_values"] == 10
    assert blocked["actionable_values"] == 0
    assert row["actionable_values"] == 0


def test_type_without_block_is_marked_presumed(rules_dir, tool_type_attr, live_category):
    """У типа без блока цели ещё нет — число помечено презумпцией, а не замером."""
    make_diameter_attribute()
    for index in range(10):
        product = make_product(f"pr{index}", f"Хомут-стяжка {index + 3} мм", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "krep-styazhki")
    assert row["binding_target"]["source"] == "presumed"
    assert row["binding_target"]["reason"] == "no_block"
    assert axis(row, "diameter")["status"] == "READY"
    # В раздел «куда уйдёт привязка» презумпции не попадают: там только факты.
    assert report["binding_targets"]["items"] == []


# --- инварианты и рейтинг ----------------------------------------------- #


def test_actionable_score_never_exceeds_potential_score(tmp_path, tool_type_attr, hand_tools_tree):
    """actionable ≤ potential — инвариант по всем типам любого скоупа."""
    make_diameter_attribute()
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"])
    for index in range(8):
        product = make_product(f"nb{index}", f"Набор бит {index + 4} шт", hand_tools_tree["leaf"])
        set_tool_type(product, tool_type_attr, "nabory-bit")
    for index in range(21):
        product = make_product(
            f"mo{index}", f"Молоток слесарный {index + 1} кг", hand_tools_tree["leaf"]
        )
        set_tool_type(product, tool_type_attr, "molotki-slesarnye")
    rules = write_rules(tmp_path, [block("klyuchi-gaechnye", "Оснастка")])

    report = run(rules, in_stock_only=True)
    assert report["candidates"]
    for row in report["candidates"]:
        assert row["actionable_score"] <= row["potential_score"]
        assert row["actionable_values"] <= row["potential_values"]
        for item in row["axes"]:
            assert item["actionable_values"] <= item["potential_values"]
    totals = report["totals"]
    assert totals["actionable_values"] <= totals["potential_values"]
    assert totals["blocked_values"] == totals["potential_values"] - totals["actionable_values"]


def test_ranking_is_sorted_by_actionable_not_potential(tmp_path, tool_type_attr, hand_tools_tree):
    """Тип с меньшим потенциалом, но видимый, идёт выше запертого гиганта."""
    make_diameter_attribute()
    make_wrenches(tool_type_attr, hand_tools_tree["leaf"], count=8)
    # treebeard кэширует состояние узла: после add_child в фикстуре экземпляр
    # устарел, и повторный add_child на нём падает — берём свежий из БД.
    root = Category.objects.get(pk=hand_tools_tree["root"].pk)
    big = root.add_child(name="Трубы", slug="truby", is_active=True, on_site=True)
    for index in range(30):
        product = make_product(f"bg{index}", f"Труба стальная {index + 3} мм", big)
        set_tool_type(product, tool_type_attr, "bolshoy-zapertyy")
    rules = write_rules(
        tmp_path,
        [
            block("klyuchi-gaechnye", "Ключи"),
            block("bolshoy-zapertyy", "Оснастка"),
        ],
    )

    report = run(rules, in_stock_only=True)
    assert [row["tool_type"] for row in report["candidates"]][0] == "klyuchi-gaechnye"
    blocked = candidate(report, "bolshoy-zapertyy")
    visible = candidate(report, "klyuchi-gaechnye")
    assert blocked["potential_values"] > visible["potential_values"]
    assert blocked["actionable_score"] == 0.0
    assert visible["actionable_score"] > 0


# --- очередь привязок и цена цели --------------------------------------- #


def test_facet_binding_queue_counts_unlocked_values(tmp_path, tool_type_attr):
    """Очередь привязок считает выигрыш и blast radius по поддереву."""
    root = Category.add_root(name="Крепёж", slug="krepezh", is_active=True, on_site=True)
    left = root.add_child(name="Стяжки", slug="styazhki", is_active=True, on_site=True)
    right = root.add_child(name="Хомуты", slug="homuty", is_active=True, on_site=True)
    Category.add_root(name="Оснастка", slug="osnastka", is_active=True, on_site=True)
    make_diameter_attribute()

    for index in range(10):
        product = make_product(f"ql{index}", f"Стяжка {index + 3} мм", left)
        set_tool_type(product, tool_type_attr, "krep-styazhki")
    for index in range(6):
        product = make_product(f"qr{index}", f"Хомут {index + 3} мм", right)
        set_tool_type(product, tool_type_attr, "krep-homuty")
    rules = write_rules(
        tmp_path,
        [block("krep-styazhki", "Оснастка"), block("krep-homuty", "Оснастка")],
    )

    queue = run(rules, in_stock_only=True)["facet_binding_queue"]
    assert queue["unlocked_values_total"] == 16
    items = {(item["attribute_slug"], item["category_id"]): item for item in queue["items"]}

    direct_left = items[("diameter", left.pk)]
    assert direct_left["binding_level"] == "direct"
    assert direct_left["unlocked_values"] == 10
    assert direct_left["blast_radius"] == 10
    assert direct_left["fill_rate"] == pytest.approx(1.0)
    assert direct_left["tool_types"] == ["krep-styazhki"]

    # Привязка к корню накрывает оба листа — это и есть blast radius.
    ancestor = items[("diameter", root.pk)]
    assert ancestor["binding_level"] == "ancestor"
    assert ancestor["unlocked_values"] == 16
    assert ancestor["blast_radius"] == 16
    assert ancestor["covers_categories"] == 2
    assert sorted(ancestor["tool_types"]) == ["krep-homuty", "krep-styazhki"]
    assert queue["items"][0]["unlocked_values"] == 16


def test_facet_binding_queue_flags_low_fill_rate(tmp_path, tool_type_attr):
    """Фасет с заполненностью в единицы процентов помечается как малополезный."""
    root = Category.add_root(name="Всё", slug="vse", is_active=True, on_site=True)
    narrow = root.add_child(name="Стяжки", slug="styazhki", is_active=True, on_site=True)
    wide = root.add_child(name="Прочее", slug="prochee", is_active=True, on_site=True)
    Category.add_root(name="Оснастка", slug="osnastka", is_active=True, on_site=True)
    make_diameter_attribute()

    for index in range(8):
        product = make_product(f"fl{index}", f"Стяжка {index + 3} мм", narrow)
        set_tool_type(product, tool_type_attr, "krep-styazhki")
    for index in range(400):
        product = make_product(f"fw{index}", f"Прочий предмет {index}", wide)
        set_tool_type(product, tool_type_attr, "prochee")
    rules = write_rules(tmp_path, [block("krep-styazhki", "Оснастка")])

    queue = run(rules, in_stock_only=True)["facet_binding_queue"]
    items = {(item["attribute_slug"], item["category_id"]): item for item in queue["items"]}
    assert items[("diameter", narrow.pk)]["low_fill_rate"] is False
    # Предложение к корню в очередь не попадает: оно накрывает одну прямую
    # категорию, то есть это тот же фасет, но с худшей заполненностью.
    assert ("diameter", root.pk) not in items


def test_binding_target_report_flags_root_binding_and_fill_rate(tmp_path, tool_type_attr):
    """Привязка в корень раздела и её цена показаны отдельно, а не спрятаны.

    Это системный дефект: имя категории блока разрешается лестницей, которая
    предпочитает ``depth == 1``, поэтому фасет ложится на весь раздел ради одного
    типа. Заполненность при этом падает до единиц процентов.
    """
    root = Category.add_root(name="Оснастка", slug="osnastka", is_active=True, on_site=True)
    leaf = root.add_child(name="Свёрла", slug="sverla-cat", is_active=True, on_site=True)
    neighbour = root.add_child(name="Прочее", slug="prochee", is_active=True, on_site=True)
    make_diameter_attribute()

    for index in range(10):
        product = make_product(f"sv{index}", f"Сверло {index + 3} мм", leaf)
        set_tool_type(product, tool_type_attr, "sverla")
    for index in range(300):
        product = make_product(f"pv{index}", f"Прочий предмет {index}", neighbour)
        set_tool_type(product, tool_type_attr, "prochee")
    rules = write_rules(tmp_path, [block("sverla", "Оснастка")])

    report = run(rules, in_stock_only=True)
    targets = {item["tool_type"]: item for item in report["binding_targets"]["items"]}
    sverla = targets["sverla"]
    assert sverla["category_id"] == root.pk
    assert sverla["category_depth"] == 1
    assert sverla["root_binding"] is True
    assert sverla["products_at_target"] == 0
    # Под фасетом окажется весь раздел, а значения получат только свёрла.
    assert sverla["blast_radius"] == 310
    assert sverla["fill_rate"] < 0.1
    assert sverla["low_fill_rate"] is True
    assert report["binding_targets"]["root_bindings"] == 1
    assert report["binding_targets"]["unresolved"] == 0


# --- сквозной рейтинг осей и прочие статусы ----------------------------- #


def test_axis_ranking_is_catalog_wide(rules_dir, tool_type_attr, live_category):
    """Рейтинг осей сквозной: одна ось складывается по всем типам сразу."""
    attribute = make_diameter_attribute()
    CategoryAttribute.objects.create(category=live_category, attribute=attribute, is_filter=True)
    for index in range(10):
        product = make_product(f"r1{index}", f"Стяжка {index + 3} мм", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")
    for index in range(7):
        product = make_product(f"r2{index}", f"Хомут {index + 3} мм", live_category)
        set_tool_type(product, tool_type_attr, "krep-homuty")

    ranking = run(rules_dir, in_stock_only=True)["axis_ranking"]
    diameter = next(e for e in ranking["by_actionable"] if e["attribute_slug"] == "diameter")
    assert diameter["tool_types"] == 2
    assert diameter["potential_values"] == 17
    assert diameter["actionable_values"] == 17
    assert diameter["statuses"] == {"READY": 2}
    # Оба порядка присутствуют и содержат одни и те же оси.
    assert {e["attribute_slug"] for e in ranking["by_actionable"]} == {
        e["attribute_slug"] for e in ranking["by_blocked"]
    }


def test_noisy_axis_is_blocked_by_purity(rules_dir, tool_type_attr, live_category):
    """Шумный шаблон — грязный пул: ось блокируется отдельной причиной."""
    Attribute.objects.create(slug="length", name="Длина", attribute_type=AttributeType.DECIMAL)
    for index in range(6):
        product = make_product(f"p{index}", f"Рулетка измерительная {index + 3} м", live_category)
        set_tool_type(product, tool_type_attr, "izm-ruletki-test")
    for index in range(4):
        product = make_product(f"pf{index}", f"Рулетка полотно {index + 16} мм", live_category)
        set_tool_type(product, tool_type_attr, "izm-ruletki-test")

    row = candidate(run(rules_dir, in_stock_only=True), "izm-ruletki-test")
    noisy = axis(row, "length")
    assert noisy["status"] == "BLOCKED_BY_PURITY"
    assert noisy["next_action"] == "POOL_PURITY_AUDIT"
    assert noisy["potential_values"] == 6
    assert noisy["actionable_values"] == 0


def test_set_and_heterogeneous_axes_carry_type_level_reason(
    rules_dir, tool_type_attr, live_category
):
    """У набора и у «свалки» блокируется каждая ось, а не только итог типа."""
    for index in range(8):
        product = make_product(f"st{index}", f"Набор бит {index + 4} шт", live_category)
        set_tool_type(product, tool_type_attr, "nabory-bit")
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
        product = make_product(f"he{index}", name, live_category)
        set_tool_type(product, tool_type_attr, "prochaya-osnastka")

    report = run(rules_dir, in_stock_only=True)
    sets = candidate(report, "nabory-bit")
    assert {item["status"] for item in sets["axes"]} == {"SKIP_SET"}
    assert {item["next_action"] for item in sets["axes"]} == {"SET_COMPOSITION_REVIEW"}
    assert sets["actionable_values"] == 0

    dump = candidate(report, "prochaya-osnastka")
    assert {item["status"] for item in dump["axes"]} == {"BLOCKED_BY_CLASSIFICATION"}
    assert {item["next_action"] for item in dump["axes"]} == {"SPLIT_TOOL_TYPE"}
    assert dump["actionable_values"] == 0
    # Потенциал при этом посчитан и виден — ради чего блокер стоит снимать.
    assert dump["potential_values"] > 0


def test_dead_category_axis_is_blocked_by_category(rules_dir, tool_type_attr):
    """Мёртвая категория — своя причина, не facet и не attribute."""
    dead = Category.add_root(name="Мёртвая", slug="dead", is_active=False, on_site=False)
    make_diameter_attribute()
    for index in range(10):
        product = make_product(f"dc{index}", f"Хомут-стяжка {index + 3} мм", dead)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    row = candidate(run(rules_dir, in_stock_only=True), "krep-styazhki")
    blocked = axis(row, "diameter")
    assert blocked["status"] == "BLOCKED_BY_CATEGORY"
    assert blocked["next_action"] == "CATEGORY_REVIVAL"
    assert blocked["live_values"] == 0
    # В очередь привязок такая ось не попадает: привязка ничего не разблокирует.
    assert run(rules_dir, in_stock_only=True)["facet_binding_queue"]["items"] == []


# --------------------------------------------------------------------- #
# Markdown-отчёт
# --------------------------------------------------------------------- #


def test_md_report_is_written_with_key_sections(rules_dir, tool_type_attr, live_category):
    """Файл создаётся и содержит все обязательные разделы отчёта."""
    for index in range(10):
        product = make_product(f"md{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    text = run_md(rules_dir, in_stock_only=True)
    assert (rules_dir / "report.md").exists()
    for section in (
        "# Кандидаты на блоки правил характеристик",
        "## Скоуп",
        "## Итоги пула",
        "## Кандидаты (по убыванию `actionable_score`)",
        "## Рейтинг осей (сквозной по каталогу)",
        "## Очередь facet-binding",
        "## Что предлагается писать",
        "## Контрольный кумулятив",
    ):
        assert section in text, section
    # Read-only заявлено в самом отчёте, а не только в документации.
    assert "read-only" in text
    # Строка про продажи — с явной деградацией, раз продаж нет.
    assert "ПРОДАЖИ:" in text and "НЕ участвует" in text
    # Числа те же, что в JSON.
    report = run(rules_dir, in_stock_only=True)
    row = candidate(report, "krep-styazhki")
    assert f"| {row['products']} |" in text
    assert f"{row['score']:.1f}" in text
    assert "krep-styazhki" in text


def test_md_report_lists_axes_with_numbers_and_examples(rules_dir, tool_type_attr, live_category):
    """По каждому кандидату — оси с попаданиями, долей, ложными и примерами."""
    for index in range(10):
        product = make_product(f"ax{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    text = run_md(rules_dir, in_stock_only=True)
    assert "`diameter`" in text
    assert "`package_quantity`" in text
    assert "regex: " in text
    assert "пример: " in text
    # Доля печатается процентом, ложные — числом.
    assert "100%" in text
    assert "| 10 | 100% | 0 |" in text


def test_md_report_stays_valid_markdown_with_pipes_in_regex(
    rules_dir, tool_type_attr, live_category
):
    """Регулярка бит содержит ``|`` — таблицы обязаны это пережить."""
    for index in range(10):
        product = make_product(f"bit{index}", f"Бита PH{index % 3 + 1} 50 мм", live_category)
        set_tool_type(product, tool_type_attr, "bity")

    text = run_md(rules_dir, in_stock_only=True)
    # Не меньше четырёх таблиц: скоуп, итоги, кандидаты, оси, кумулятив.
    assert assert_markdown_tables_are_valid(text) >= 4
    # Регулярка с трубой уехала в инлайн-код, а не в текст.
    assert "`(?<![а-яёa-z\\d])(ph|pz|tx|t|sl|hex|torx)" in text


def test_md_report_respects_limit(rules_dir, tool_type_attr, live_category):
    for index in range(10):
        product = make_product(f"l1{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")
    for index in range(10):
        product = make_product(f"l2{index}", f"Молоток слесарный {index + 1} кг", live_category)
        set_tool_type(product, tool_type_attr, "molotki-slesarnye")

    full = run_md(rules_dir, in_stock_only=True)
    assert "molotki-slesarnye" in full

    limited = run_md(rules_dir, in_stock_only=True, limit=1)
    assert "и ещё 1 типов" in limited
    # Итоги считаются по всему скоупу, срез влияет только на вывод.
    assert "| товаров в скоупе | 20 |" in limited


def test_md_report_survives_empty_scope(rules_dir, tool_type_attr):
    text = run_md(rules_dir, in_stock_only=True)
    assert "Кандидатов нет" in text
    assert assert_markdown_tables_are_valid(text) >= 3


def test_both_reports_are_written_independently(rules_dir, tool_type_attr, live_category):
    """Оба формата можно попросить одновременно, и они не мешают друг другу."""
    for index in range(10):
        product = make_product(f"b{index}", f"Хомут-стяжка {index + 3} мм 50 шт", live_category)
        set_tool_type(product, tool_type_attr, "krep-styazhki")

    json_path = rules_dir / "both.json"
    md_path = rules_dir / "both.md"
    call_command(
        "discover_missing_rules",
        path=str(rules_dir),
        json_report=str(json_path),
        md_report=str(md_path),
        in_stock_only=True,
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))
    text = md_path.read_text(encoding="utf-8")
    assert report["candidates"][0]["tool_type"] == "krep-styazhki"
    assert "krep-styazhki" in text
    assert assert_markdown_tables_are_valid(text) >= 4

    # И каждый формат работает в одиночку.
    only_json = rules_dir / "only.json"
    call_command(
        "discover_missing_rules",
        path=str(rules_dir),
        json_report=str(only_json),
        in_stock_only=True,
    )
    assert only_json.exists()
    only_md = rules_dir / "only.md"
    call_command(
        "discover_missing_rules",
        path=str(rules_dir),
        md_report=str(only_md),
        in_stock_only=True,
    )
    assert only_md.exists()


def test_both_formats_print_axis_breakdown_and_two_scores(
    tmp_path, tool_type_attr, hand_tools_tree, capsys
):
    """Разбивку по осям со статусами и оба score печатают ОБА формата.

    Тип собран так, что оси расходятся: `diameter` уже привязан к категории
    товаров и виден, `package_quantity` — нет, а цель блока («Оснастка») товары
    не накрывает. Ровно случай `klyuchi-gaechnye`, ради которого счёт по осям и
    делался.
    """
    diameter = make_diameter_attribute()
    Attribute.objects.create(
        slug="package_quantity", name="Фасовка", attribute_type=AttributeType.DECIMAL
    )
    for index in range(10):
        product = make_product(
            f"bf{index}", f"Ключ гаечный {index + 8} мм 50 шт", hand_tools_tree["leaf"]
        )
        set_tool_type(product, tool_type_attr, "klyuchi-gaechnye")
    CategoryAttribute.objects.create(
        category=hand_tools_tree["leaf"], attribute=diameter, is_filter=True
    )
    rules_dir = write_rules(tmp_path, [block("klyuchi-gaechnye", "Оснастка")])

    md_path = rules_dir / "axes.md"
    json_path = rules_dir / "axes.json"
    call_command(
        "discover_missing_rules",
        path=str(rules_dir),
        md_report=str(md_path),
        json_report=str(json_path),
        in_stock_only=True,
    )
    console = capsys.readouterr().out
    text = md_path.read_text(encoding="utf-8")
    row = candidate(json.loads(json_path.read_text(encoding="utf-8")), "klyuchi-gaechnye")

    for output in (console, text):
        # Обе оси названы поимённо, с обоими статусами.
        assert "diameter" in output
        assert "package_quantity" in output
        assert "READY" in output
        assert "BLOCKED_BY_FACET" in output
        assert "FACET_BINDING_AUDIT" in output
        # Оба score и три числа — рядом, а не вместо друг друга.
        assert "potential" in output and "actionable" in output
        assert str(row["potential_values"]) in output
        assert f"{row['actionable_score']:.1f}" in output
        assert f"{row['potential_score']:.1f}" in output

    # Консоль печатает разбивку в формате владельца.
    assert "potential: 10" in console
    assert "actionable: 0" in console
    assert "visibility: 0%" in console
    assert "next_action: FACET_BINDING_AUDIT" in console
    assert "potential_total:  20" in console
    assert "actionable_total: 10" in console
    assert "actionable_ratio: 50.0%" in console
    # Markdown остаётся валидной разметкой с новыми таблицами.
    assert assert_markdown_tables_are_valid(text) >= 6


def test_md_report_writes_nothing_to_db(rules_dir, tool_type_attr, live_category):
    """Второй формат выхода не отменяет главного свойства команды."""
    for index in range(8):
        product = make_product(f"mdw{index}", f"Отвертка {index * 2} мм PH2", live_category)
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
    run_md(rules_dir, in_stock_only=True, active_only=True)
    assert snapshot() == before
