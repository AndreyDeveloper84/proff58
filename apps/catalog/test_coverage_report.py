"""Тесты coverage-отчёта (#225): метрика покрытия + правило включения (§10.4, §17)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.management.commands.coverage_report import (
    REC_EXTRA,
    REC_HIDE,
    REC_MAIN,
    recommend,
)
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
    StockStatus,
)

# --- правило включения (§10.4): процент + абсолют + кураторское закрепление ---


def test_recommend_bands():
    # основной: >=30% и достаточный абсолют
    assert recommend(80, 16, False, 3, 50) == REC_MAIN
    # дополнительный: 5–30% и достаточный абсолют
    assert recommend(20, 4, False, 3, 50) == REC_EXTRA
    # скрыть: мало и по проценту, и по абсолюту
    assert recommend(5, 1, False, 3, 50) == REC_HIDE


def test_recommend_abs_gate_overrides_high_pct():
    # высокий %, но абсолют ниже min_abs → не «основной» (§10.4: 20×10% = 2 бессмысленно)
    assert recommend(80, 2, False, 3, 50) == REC_HIDE


def test_recommend_large_abs_rescues_low_pct():
    # низкий %, но абсолютно много штук → хотя бы «дополнительный» (10000×4% = 400)
    assert recommend(4, 400, False, 10, 100) == REC_EXTRA


def test_recommend_curator_pin_forces_main():
    # кураторское закрепление перекрывает любой низкий coverage/абсолют
    assert recommend(3, 1, True, 10, 100) == REC_MAIN


def test_recommend_uses_exact_pct_not_rounded():
    # граница 30%: 29.5% НЕ должно округляться вверх → остаётся «дополнительный»
    assert recommend(29.5, 50, False, 10, 1000) == REC_EXTRA
    assert recommend(30.0, 50, False, 10, 1000) == REC_MAIN
    # граница 5%: 4.5% не округляется до 5% → «скрыть»
    assert recommend(4.5, 50, False, 10, 1000) == REC_HIDE


# --- интеграционный прогон команды на синтетике ---


@pytest.fixture
def shop(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    leaf = root.add_child(name="Инструмент", slug="inst")

    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    power = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER, is_filterable=True
    )
    chuck = Attribute.objects.create(
        slug="chuck", name="Патрон", attribute_type=AttributeType.SELECT, is_filterable=True
    )
    rare = Attribute.objects.create(
        slug="rare", name="Редкий", attribute_type=AttributeType.INTEGER, is_filterable=True
    )
    material = Attribute.objects.create(
        slug="material", name="Материал", attribute_type=AttributeType.SELECT, is_filterable=True
    )
    for a in (tool_type, power, chuck, rare):
        CategoryAttribute.objects.create(category=leaf, attribute=a)
    # material — кураторское закрепление (прокси is_seo_facet)
    CategoryAttribute.objects.create(category=leaf, attribute=material, is_seo_facet=True)

    perf = AttributeOption.objects.create(
        attribute=tool_type, value="Перфораторы", slug="perforatory"
    )

    # 20 перфораторов: power у 16 (80%), chuck у 4 (20%), rare у 1 (5%), material у 2 (10%, pinned)
    for i in range(20):
        attrs = {"tool_type": "Перфораторы"}
        if i < 16:
            attrs["power"] = 800 + i
        if i < 4:
            attrs["chuck"] = "Быстрозажимной"
        if i < 1:
            attrs["rare"] = 1
        if i < 2:
            attrs["material"] = "Сталь"
        p = Product.objects.create(
            category=leaf,
            name=f"perf{i}",
            slug=f"perf-{i}",
            attrs_cache=attrs,
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_status=StockStatus.IN_STOCK,
        )
        ProductAttributeValue.objects.create(product=p, attribute=tool_type, value_option=perf)
    return {"leaf": leaf, "perf": perf}


def _run(**kwargs):
    out = StringIO()
    call_command("coverage_report", stdout=out, **kwargs)
    return out.getvalue()


def _line(out: str, slug: str) -> str:
    return next(ln for ln in out.splitlines() if ln.strip().startswith(slug))


@pytest.mark.django_db
def test_report_coverage_and_recommendations(shop):
    out = _run(tool_type="perforatory", min_abs=3, large_abs=50)
    assert "товаров 20" in out
    # power 80% → основной
    assert "80%" in _line(out, "power") and REC_MAIN in _line(out, "power")
    # chuck 20% → дополнительный
    assert "20%" in _line(out, "chuck") and REC_EXTRA in _line(out, "chuck")
    # rare 5%, abs 1 < min_abs → скрыть
    assert "5%" in _line(out, "rare") and REC_HIDE in _line(out, "rare")
    # material 10% но pinned (is_seo_facet) → основной
    assert REC_MAIN in _line(out, "material")


@pytest.mark.django_db
def test_report_topn_without_tool_type(shop):
    out = _run(top=5)
    # без --tool-type берёт топ типов по числу товаров — наш единственный тип присутствует
    assert "perforatory" in out and "товаров 20" in out


@pytest.mark.django_db
def test_report_markdown_format(shop):
    out = _run(tool_type="perforatory", min_abs=3, format="md")
    assert "| Атрибут | Coverage % | Abs | Рекомендация |" in out
    assert "| power | 80% | 16/20 |" in out


@pytest.mark.django_db
def test_report_empty_db_warns(db):
    out = _run()
    assert "не найдено" in out
