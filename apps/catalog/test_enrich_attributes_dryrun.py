"""Штатный dry-run ``enrich_attributes`` (окно CODE-01): «показать и не писать».

Поверх реального словаря ``data/attribute_rules.json`` (через call_command) проверяем:

- по-позиционный отчёт: ``product_id`` / ``tool_type`` / ``attribute`` /
  ``current_value`` / ``proposed_value`` / ``source_fragment`` / ``action`` / ``reason``;
- каждый исход ``action``: create / update / skip (приоритет) / prune / keep;
- dry-run ничего не пишет: снимки PAV, ``attrs_cache`` и ``ImportRun`` до/после
  идентичны;
- эквивалентность: решения dry-run совпадают с тем, что реально записывает apply
  (ключевое требование владельца — один extraction/write-decision path);
- пишущий режим не изменился: ImportRun создаётся, команда возвращает его pk.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    ImportRun,
    Product,
    ProductAttributeValue,
    Source,
)
from apps.catalog.read_models import attr_value_to_json

REQUIRED_ROW_FIELDS = {
    "product_id",
    "tool_type",
    "attribute",
    "current_value",
    "proposed_value",
    "source_fragment",
    "action",
    "reason",
}


@pytest.fixture
def catalog(db):
    """Топ-категория «Электроинструмент» + атрибут tool_type с вариантом «Дрели…»."""
    top = Category.add_root(name="Электроинструмент", slug="elektroinstrument", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    option = AttributeOption.objects.create(
        attribute=tool_type, value="Дрели и шуруповёрты", slug="dreli-shurupoverty"
    )
    return {"top": top, "tool_type": tool_type, "option": option}


def _make_product(catalog, name, code):
    """Товар с tool_type=Дрели и шуруповёрты (как после enrich_tool_type)."""
    product = Product.objects.create(category=catalog["top"], name=name, slug=code, code_1c=code)
    ProductAttributeValue.objects.create(
        product=product,
        attribute=catalog["tool_type"],
        value_option=catalog["option"],
        source=Source.MANUAL,
    )
    return product


def _dry_run_report(*args):
    """Прогнать enrich_attributes --dry-run и вернуть распарсенный JSON-отчёт.

    Без ``--json-report`` machine-readable JSON идёт в stdout, человекочитаемая
    сводка — в stderr, поэтому stdout обязан парситься как чистый JSON.
    """
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--dry-run", *args, stdout=out, stderr=err)
    return json.loads(out.getvalue())


def _pav_snapshot():
    """Полный снимок PAV: значение (JSON-ядро), источник и confidence."""
    return {
        (pav.product_id, pav.attribute.slug): (
            attr_value_to_json(pav),
            pav.source,
            pav.confidence,
        )
        for pav in ProductAttributeValue.objects.select_related("attribute", "value_option")
    }


def _cache_snapshot():
    return dict(Product.objects.values_list("id", "attrs_cache"))


def _rows_by(report, action):
    return [r for r in report["rows"] if r["action"] == action]


# --- по-позиционный отчёт -------------------------------------------------


@pytest.mark.django_db
def test_dry_run_reports_create_rows_with_all_required_fields(catalog):
    product = _make_product(catalog, "Дрель-шуруповёрт аккумуляторный 18В бесщёточный 55 Нм", "d1")
    call_command("load_attributes")

    report = _dry_run_report()

    assert report["mode"] == "dry-run"
    assert report["rows"], "dry-run обязан показать по-позиционные решения"
    for row in report["rows"]:
        assert REQUIRED_ROW_FIELDS <= set(row), f"в строке нет полей: {row}"

    voltage = next(r for r in report["rows"] if r["attribute"] == "voltage")
    assert voltage["action"] == "create"
    assert voltage["product_id"] == product.id
    assert voltage["tool_type"] == "dreli-shurupoverty"  # slug из PAV, не из attrs_cache
    assert voltage["current_value"] is None
    assert voltage["proposed_value"] == 18.0
    assert voltage["source_fragment"]  # фрагмент названия, из которого извлечено
    assert voltage["reason"]


@pytest.mark.django_db
def test_dry_run_report_only_alias_works(catalog):
    _make_product(catalog, "Дрель-шуруповёрт 18В", "d2")
    call_command("load_attributes")

    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--report-only", stdout=out, stderr=err)
    report = json.loads(out.getvalue())
    assert report["mode"] == "dry-run"
    assert _rows_by(report, "create")


@pytest.mark.django_db
def test_dry_run_aggregates_match_rows(catalog):
    _make_product(catalog, "Дрель-шуруповёрт аккумуляторный 18В 55 Нм", "a1")
    _make_product(catalog, "Дрель-шуруповёрт сетевая 12В", "a2")
    call_command("load_attributes")

    report = _dry_run_report()

    rows = report["rows"]
    by_tt = report["by_tool_type"]["dreli-shurupoverty"]
    assert by_tt["total"] == len(rows)
    for action, count in by_tt["by_action"].items():
        assert count == len(_rows_by(report, action))

    for slug, agg in report["by_attribute"].items():
        attr_rows = [r for r in rows if r["attribute"] == slug]
        assert agg["total"] == len(attr_rows)
        for action, count in agg["by_action"].items():
            assert count == len([r for r in attr_rows if r["action"] == action])


@pytest.mark.django_db
def test_dry_run_json_report_file(catalog, tmp_path):
    _make_product(catalog, "Дрель-шуруповёрт 18В", "j1")
    call_command("load_attributes")

    report_path = tmp_path / "report.json"
    out, err = StringIO(), StringIO()
    call_command(
        "enrich_attributes",
        "--dry-run",
        "--json-report",
        str(report_path),
        stdout=out,
        stderr=err,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["rows"]
    # stdout — человекочитаемая сводка, НЕ JSON (JSON — в файле).
    assert "Характеристики" in out.getvalue()


# --- действия: update / skip / prune / keep --------------------------------


@pytest.mark.django_db
def test_dry_run_reports_update_when_priority_allows(catalog):
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "u1")
    call_command("load_attributes")
    voltage = Attribute.objects.get(slug="voltage")
    ProductAttributeValue.objects.create(
        product=product, attribute=voltage, value_decimal=Decimal("12"), source=Source.REGEX
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "update") if r["attribute"] == "voltage")
    assert row["current_value"] == 12.0
    assert row["proposed_value"] == 18.0
    assert row["source_fragment"]


@pytest.mark.django_db
def test_dry_run_reports_skip_for_manual(catalog):
    """Приоритетная защита: manual (100) не перезаписывается regex (40)."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "s1")
    call_command("load_attributes")
    voltage = Attribute.objects.get(slug="voltage")
    ProductAttributeValue.objects.create(
        product=product, attribute=voltage, value_decimal=Decimal("99"), source=Source.MANUAL
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "skip") if r["attribute"] == "voltage")
    assert row["current_value"] == 99.0
    assert row["proposed_value"] == 18.0
    assert "приоритет" in row["reason"]


@pytest.mark.django_db
def test_dry_run_reports_skip_for_import_1c(catalog):
    """Приоритетная защита: import_1c (60) не перезаписывается regex (40)."""
    product = _make_product(catalog, "Дрель-шуруповёрт 55 Нм", "s2")
    call_command("load_attributes")
    torque = Attribute.objects.get(slug="torque")
    ProductAttributeValue.objects.create(
        product=product, attribute=torque, value_decimal=Decimal("10"), source=Source.IMPORT_1C
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "skip") if r["attribute"] == "torque")
    assert row["current_value"] == 10.0
    assert row["proposed_value"] == 55.0


@pytest.mark.django_db
def test_dry_run_reports_prune_for_stale_engine_value(catalog):
    """Движок больше не извлекает torque (в названии нет «Нм») → prune regex-значения."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "p1")
    call_command("load_attributes")
    torque = Attribute.objects.get(slug="torque")
    ProductAttributeValue.objects.create(
        product=product, attribute=torque, value_decimal=Decimal("5"), source=Source.REGEX
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "prune") if r["attribute"] == "torque")
    assert row["current_value"] == 5.0
    assert row["proposed_value"] is None


@pytest.mark.django_db
def test_dry_run_reports_keep_for_non_prunable_source(catalog):
    """manual-значение по управляемому атрибуту, который движок не извлёк, — keep."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "k1")
    call_command("load_attributes")
    torque = Attribute.objects.get(slug="torque")
    ProductAttributeValue.objects.create(
        product=product, attribute=torque, value_decimal=Decimal("42"), source=Source.MANUAL
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "keep") if r["attribute"] == "torque")
    assert row["current_value"] == 42.0
    assert row["proposed_value"] is None


@pytest.mark.django_db
def test_dry_run_reports_keep_when_value_unchanged(catalog):
    """Если значение совпадает и источник тот же — keep, не update."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "k2")
    call_command("load_attributes")
    voltage = Attribute.objects.get(slug="voltage")
    ProductAttributeValue.objects.create(
        product=product, attribute=voltage, value_decimal=Decimal("18.0"), source=Source.REGEX
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "keep") if r["attribute"] == "voltage")
    assert row["current_value"] == 18.0
    assert row["proposed_value"] == 18.0
    assert "не изменилось" in row["reason"]


@pytest.mark.django_db
def test_dry_run_reports_update_when_source_priority_higher_same_value(catalog):
    """Если значение совпадает, но источник выше приоритетом — update (меняем provenance)."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "k3")
    call_command("load_attributes")
    voltage = Attribute.objects.get(slug="voltage")
    ProductAttributeValue.objects.create(
        product=product, attribute=voltage, value_decimal=Decimal("18"), source=Source.KEYWORD
    )

    report = _dry_run_report()

    row = next(r for r in _rows_by(report, "update") if r["attribute"] == "voltage")
    assert row["current_value"] == 18.0
    assert row["proposed_value"] == 18.0
    assert row["source"] == Source.REGEX
    assert "происхождения" in row["reason"]


# --- dry-run ничего не пишет ----------------------------------------------


@pytest.mark.django_db
def test_dry_run_writes_nothing(catalog):
    """Снимки PAV, attrs_cache и ImportRun до/после dry-run — идентичны."""
    product = _make_product(catalog, "Дрель-шуруповёрт аккумуляторный 18В 55 Нм", "w1")
    call_command("load_attributes")
    torque = Attribute.objects.get(slug="torque")
    ProductAttributeValue.objects.create(
        product=product, attribute=torque, value_decimal=Decimal("5"), source=Source.REGEX
    )

    pav_before = _pav_snapshot()
    cache_before = _cache_snapshot()
    runs_before = ImportRun.objects.count()

    report = _dry_run_report()
    assert report["rows"]  # отчёт непуст — решения принимались

    assert _pav_snapshot() == pav_before, "dry-run изменил ProductAttributeValue"
    assert _cache_snapshot() == cache_before, "dry-run изменил attrs_cache"
    assert ImportRun.objects.count() == runs_before, "dry-run создал ImportRun"


# --- эквивалентность dry-run и apply ---------------------------------------


@pytest.mark.django_db
def test_dry_run_decisions_match_apply(catalog):
    """Ключевое доказательство: dry-run предсказывает ровно то, что пишет apply.

    Смешанный набор: create (n1), skip manual + prune regex (n2), update regex (n3),
    keep manual (n4). Снимок PAV до прогона + строки dry-run → предсказанное
    финальное состояние; оно обязано совпасть с реальным после apply, включая
    attrs_cache управляемых ключей.
    """
    _make_product(catalog, "Дрель-шуруповёрт аккумуляторный 18В бесщёточный 55 Нм", "n1")
    p2 = _make_product(catalog, "Дрель-шуруповёрт 12В", "n2")
    p3 = _make_product(catalog, "Дрель-шуруповёрт 36В 70 Нм", "n3")
    p4 = _make_product(catalog, "Дрель-шуруповёрт 24В", "n4")
    call_command("load_attributes")
    voltage = Attribute.objects.get(slug="voltage")
    torque = Attribute.objects.get(slug="torque")
    # n2: manual voltage → skip; regex torque без «Нм» в названии → prune.
    ProductAttributeValue.objects.create(
        product=p2, attribute=voltage, value_decimal=Decimal("99"), source=Source.MANUAL
    )
    ProductAttributeValue.objects.create(
        product=p2, attribute=torque, value_decimal=Decimal("5"), source=Source.REGEX
    )
    # n3: regex voltage 12 → update на 36 (regex ≥ regex).
    ProductAttributeValue.objects.create(
        product=p3, attribute=voltage, value_decimal=Decimal("12"), source=Source.REGEX
    )
    # n4: manual torque без «Нм» в названии → keep.
    ProductAttributeValue.objects.create(
        product=p4, attribute=torque, value_decimal=Decimal("42"), source=Source.MANUAL
    )

    before = _pav_snapshot()
    report = _dry_run_report()
    assert _pav_snapshot() == before  # сам dry-run ничего не записал

    # Предсказание: применяем строки отчёта к снимку «до».
    predicted = dict(before)
    for row in report["rows"]:
        key = (row["product_id"], row["attribute"])
        if row["action"] == "create":
            assert key not in before
            predicted[key] = (row["proposed_value"], row["source"], None)
        elif row["action"] == "update":
            assert key in before
            assert before[key][0] == row["current_value"]
            predicted[key] = (row["proposed_value"], row["source"], None)
        elif row["action"] == "prune":
            assert key in before
            predicted.pop(key)
        elif row["action"] in ("skip", "keep"):
            assert key in before
            assert before[key][0] == row["current_value"]
        else:  # pragma: no cover - неизвестный action = провал контракта
            raise AssertionError(f"неожиданный action: {row['action']}")

    call_command("enrich_attributes")  # боевой apply

    after = _pav_snapshot()
    assert set(after) == set(predicted), "apply изменил набор PAV не так, как предсказал dry-run"
    for key, (value, source, _) in predicted.items():
        got_value, got_source, _ = after[key]
        assert got_value == value, f"{key}: apply записал {got_value}, dry-run предсказал {value}"
        if source is not None:
            assert got_source == source, f"{key}: источник {got_source} != предсказанного {source}"

    # attrs_cache: управляемые ключи совпадают с предсказанными create/update,
    # prune-ключи отсутствуют.
    proposed_by_product: dict[int, dict[str, object]] = {}
    pruned_by_product: dict[int, set[str]] = {}
    for row in report["rows"]:
        if row["action"] in ("create", "update"):
            proposed_by_product.setdefault(row["product_id"], {})[row["attribute"]] = row[
                "proposed_value"
            ]
        elif row["action"] == "prune":
            pruned_by_product.setdefault(row["product_id"], set()).add(row["attribute"])
    for product_id, expected in proposed_by_product.items():
        cache = Product.objects.get(id=product_id).attrs_cache
        for slug, value in expected.items():
            assert cache[slug] == value, f"{product_id}/{slug}: cache {cache.get(slug)} != {value}"
    for product_id, slugs in pruned_by_product.items():
        cache = Product.objects.get(id=product_id).attrs_cache
        for slug in slugs:
            assert slug not in cache, f"{product_id}/{slug}: prune-ключ остался в attrs_cache"


# --- пишущий режим не изменился --------------------------------------------


@pytest.mark.django_db
def test_apply_mode_unchanged(catalog):
    """Без --dry-run поведение прежнее: ImportRun создан, возвращён его pk, значения записаны."""
    product = _make_product(catalog, "Дрель-шуруповёрт аккумуляторный 18В 55 Нм", "z1")
    call_command("load_attributes")
    runs_before = ImportRun.objects.count()

    out = StringIO()
    result = call_command("enrich_attributes", stdout=out)

    assert ImportRun.objects.count() == runs_before + 1
    run = ImportRun.objects.latest("id")
    assert result == str(run.pk)
    assert run.status == "done"
    pav = ProductAttributeValue.objects.get(product=product, attribute__slug="voltage")
    assert pav.value_decimal == Decimal("18")
    product.refresh_from_db()
    assert product.attrs_cache["voltage"] == 18.0
