"""ХАР-PRE: dry-run/plan ``load_attributes`` + три дефекта загрузчика схемы.

Окно ХАР-PRE (задание владельца 2026-08-08). Проверяем:

1. **Дефект «size.unit»** — словарь объявляет slug ``size`` в трёх блоках tool_type:
   ``klyuchi-gaechnye``/``golovki`` (number, unit «мм») и ``siz-perchatki``
   (select, unit отсутствует). Последний блок затирал единицу измерения пустой
   строкой. Инвариант: **пустое значение в правилах не перезаписывает непустое в БД**.
2. **Дефект «мёртвый одноимённый корень»** — ``_bind_category`` брал первый по pk
   узел depth=1 без учёта активности, поэтому фасеты садились на легаси-корень
   (is_active=False/on_site=False), а не на витринный. Инвариант: при
   неоднозначности имени живые (is_active AND on_site) кандидаты имеют приоритет.
3. **Дефект «тихий WARNING»** — неоднозначность и отсутствие категории не
   различались и не влияли на исход. Инвариант: ``ambiguous`` — fail-closed по
   умолчанию (флаг ``--allow-ambiguous`` продолжает, пропуская), ``not_found`` —
   предупреждение с кодом причины (флаг ``--strict-bindings`` делает фатальным).

Плюс сам dry-run: ничего не пишет, печатает machine-readable план
(create/update/keep + было→станет) и совпадает с тем, что реально делает apply.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
)

REQUIRED_ATTRIBUTE_FIELDS = {"slug", "action", "current", "target", "changes", "declared_in"}
REQUIRED_BINDING_FIELDS = {"category", "attribute", "action", "status", "candidates", "reason"}


def _rules(tool_types: list[dict]) -> dict:
    return {"version": "test", "source_priority": {}, "tool_types": tool_types}


def _write_rules(tmp_path, tool_types: list[dict]) -> str:
    (tmp_path / "attribute_rules.json").write_text(
        json.dumps(_rules(tool_types), ensure_ascii=False), encoding="utf-8"
    )
    return str(tmp_path)


def _plan(path: str, *args) -> dict:
    """Прогнать dry-run и вернуть разобранный JSON-план."""
    out = StringIO()
    call_command("load_attributes", "--path", path, "--dry-run", *args, stdout=out)
    return json.loads(out.getvalue())


# --------------------------------------------------------------------------- #
# Дефект 1: пустой unit в правилах затирал непустой unit в БД
# --------------------------------------------------------------------------- #

SIZE_NUMBER = {
    "tool_type": "klyuchi-gaechnye",
    "category": "Ручной инструмент",
    "attributes": [
        {"slug": "size", "name": "Размер «под ключ»", "kind": "number", "unit": "мм"},
    ],
}
SIZE_SELECT = {
    "tool_type": "siz-perchatki",
    "category": "Перчатки и рукавицы",
    "attributes": [
        {
            "slug": "size",
            "name": "Размер",
            "kind": "select",
            "options": [{"value": "M", "slug": "m"}],
        },
    ],
}


@pytest.mark.django_db
def test_empty_unit_in_rules_does_not_wipe_existing_unit(tmp_path):
    """Дефект 1: блок без ``unit`` не должен стирать «мм» у уже созданного атрибута."""
    path = _write_rules(tmp_path, [SIZE_NUMBER, SIZE_SELECT])
    call_command("load_attributes", "--path", path)

    assert Attribute.objects.get(slug="size").unit == "мм"


@pytest.mark.django_db
def test_empty_unit_does_not_wipe_unit_set_in_db_beforehand(tmp_path):
    """Тот же инвариант для атрибута, единицу которому проставили руками в БД."""
    Attribute.objects.create(
        slug="size", name="Размер", attribute_type=AttributeType.DECIMAL, unit="мм"
    )
    path = _write_rules(tmp_path, [SIZE_SELECT])
    call_command("load_attributes", "--path", path)

    assert Attribute.objects.get(slug="size").unit == "мм"


@pytest.mark.django_db
def test_non_empty_unit_from_rules_still_overwrites(tmp_path):
    """Защита минимальна: непустое значение из правил по-прежнему перезаписывает."""
    Attribute.objects.create(
        slug="size", name="Размер", attribute_type=AttributeType.DECIMAL, unit="см"
    )
    path = _write_rules(tmp_path, [SIZE_NUMBER])
    call_command("load_attributes", "--path", path)

    assert Attribute.objects.get(slug="size").unit == "мм"


@pytest.mark.django_db
def test_real_rules_keep_size_unit():
    """Боевой словарь: после загрузки у ``size`` остаётся «мм»."""
    Category.add_root(name="Ручной инструмент", slug="ruchnoy", on_site=True)
    call_command("load_attributes")

    assert Attribute.objects.get(slug="size").unit == "мм"


@pytest.mark.django_db
def test_plan_reports_suppressed_unit_overwrite(tmp_path):
    """Подавление видно в плане: поле, было→станет и код причины."""
    Attribute.objects.create(
        slug="size",
        name="Размер",
        attribute_type=AttributeType.DECIMAL,
        unit="мм",
        is_filterable=True,
    )
    path = _write_rules(tmp_path, [SIZE_SELECT])
    plan = _plan(path)

    row = next(r for r in plan["attributes"] if r["slug"] == "size")
    assert row["action"] == "keep"
    assert row["changes"] == []
    assert row["suppressed"] == [
        {"field": "unit", "from": "мм", "to": "", "reason": "empty_rule_value"}
    ]


# --------------------------------------------------------------------------- #
# Дефект 2: привязка уходила на мёртвый одноимённый корень
# --------------------------------------------------------------------------- #

HAND_TOOL = {
    "tool_type": "klyuchi-gaechnye",
    "category": "Ручной инструмент",
    "attributes": [{"slug": "size", "name": "Размер", "kind": "number", "unit": "мм"}],
}


def _two_roots_same_name() -> tuple[Category, Category]:
    """Мёртвый легаси-корень (меньший pk) и живой витринный — одно имя, depth=1."""
    legacy = Category.add_root(
        name="Ручной инструмент",
        slug="ruchnoy-instrument",
        is_active=False,
        on_site=False,
        is_site_v2=False,
    )
    live = Category.add_root(
        name="Ручной инструмент",
        slug="ruchnoy",
        is_active=True,
        on_site=True,
        is_site_v2=True,
    )
    assert legacy.pk < live.pk
    return legacy, live


@pytest.mark.django_db
def test_binds_to_live_root_not_dead_legacy(tmp_path):
    """Дефект 2: при одинаковом имени на depth=1 выигрывает живой узел."""
    legacy, live = _two_roots_same_name()
    path = _write_rules(tmp_path, [HAND_TOOL])
    call_command("load_attributes", "--path", path)

    assert CategoryAttribute.objects.filter(category=live, attribute__slug="size").exists()
    assert not CategoryAttribute.objects.filter(category=legacy, attribute__slug="size").exists()


@pytest.mark.django_db
def test_plan_shows_live_resolution_with_candidates(tmp_path):
    """План объясняет выбор: код причины + полный список кандидатов."""
    legacy, live = _two_roots_same_name()
    path = _write_rules(tmp_path, [HAND_TOOL])
    plan = _plan(path)

    row = next(r for r in plan["bindings"] if r["attribute"] == "size")
    assert REQUIRED_BINDING_FIELDS <= set(row)
    assert row["status"] == "bound"
    assert row["reason"] == "bound:top:live"
    assert row["category_id"] == live.pk
    assert {c["id"] for c in row["candidates"]} == {legacy.pk, live.pk}


@pytest.mark.django_db
def test_single_inactive_candidate_still_binds(tmp_path):
    """Обратная совместимость: если живых кандидатов нет вовсе — биндим как раньше."""
    only = Category.add_root(
        name="Ручной инструмент", slug="ruchnoy-instrument", is_active=False, on_site=False
    )
    path = _write_rules(tmp_path, [HAND_TOOL])
    call_command("load_attributes", "--path", path)

    assert CategoryAttribute.objects.filter(category=only, attribute__slug="size").exists()


# --------------------------------------------------------------------------- #
# Дефект 3: неоднозначность и отсутствие категории были тихим WARNING
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_ambiguous_binding_is_fail_closed(tmp_path):
    """Дефект 3: два живых одноимённых кандидата — команда падает, а не гадает."""
    Category.add_root(name="Ручной инструмент", slug="ruchnoy-a", is_active=True, on_site=True)
    Category.add_root(name="Ручной инструмент", slug="ruchnoy-b", is_active=True, on_site=True)
    path = _write_rules(tmp_path, [HAND_TOOL])

    with pytest.raises(CommandError) as exc:
        call_command("load_attributes", "--path", path)

    assert "Ручной инструмент" in str(exc.value)
    # fail-closed: не записано вообще ничего, включая атрибуты.
    assert not Attribute.objects.filter(slug="size").exists()
    assert not CategoryAttribute.objects.exists()


@pytest.mark.django_db
def test_allow_ambiguous_skips_binding_but_loads_schema(tmp_path):
    """Флаг «продолжить, пропустив неоднозначные»: схема грузится, привязки нет."""
    Category.add_root(name="Ручной инструмент", slug="ruchnoy-a", is_active=True, on_site=True)
    Category.add_root(name="Ручной инструмент", slug="ruchnoy-b", is_active=True, on_site=True)
    path = _write_rules(tmp_path, [HAND_TOOL])

    call_command("load_attributes", "--path", path, "--allow-ambiguous")

    assert Attribute.objects.filter(slug="size").exists()
    assert not CategoryAttribute.objects.exists()


@pytest.mark.django_db
def test_plan_lists_ambiguous_candidates(tmp_path):
    """План перечисляет кандидатов неоднозначности с их признаками."""
    a = Category.add_root(name="Ручной инструмент", slug="ruchnoy-a", is_active=True, on_site=True)
    b = Category.add_root(name="Ручной инструмент", slug="ruchnoy-b", is_active=True, on_site=True)
    path = _write_rules(tmp_path, [HAND_TOOL])
    plan = _plan(path, "--allow-ambiguous")

    row = next(r for r in plan["bindings"] if r["attribute"] == "size")
    assert row["status"] == "ambiguous"
    assert row["reason"] == "ambiguous:top"
    assert row["action"] == "skip"
    assert row["category_id"] is None
    assert {c["id"] for c in row["candidates"]} == {a.pk, b.pk}
    assert {c["slug"] for c in row["candidates"]} == {"ruchnoy-a", "ruchnoy-b"}
    assert plan["summary"]["bindings"]["ambiguous"] == 1


@pytest.mark.django_db
def test_missing_category_is_warning_by_default(tmp_path):
    """Отсутствие категории не фатально: привязать некуда — но и испортить нечего."""
    path = _write_rules(tmp_path, [HAND_TOOL])
    call_command("load_attributes", "--path", path)

    assert Attribute.objects.filter(slug="size").exists()
    assert not CategoryAttribute.objects.exists()


@pytest.mark.django_db
def test_missing_category_is_fatal_under_strict_bindings(tmp_path):
    """``--strict-bindings`` требует полного дерева."""
    path = _write_rules(tmp_path, [HAND_TOOL])

    with pytest.raises(CommandError) as exc:
        call_command("load_attributes", "--path", path, "--strict-bindings")

    assert "Ручной инструмент" in str(exc.value)
    assert not Attribute.objects.filter(slug="size").exists()


@pytest.mark.django_db
def test_plan_marks_missing_category(tmp_path):
    path = _write_rules(tmp_path, [HAND_TOOL])
    plan = _plan(path)

    row = next(r for r in plan["bindings"] if r["attribute"] == "size")
    assert row["status"] == "not_found"
    assert row["reason"] == "not_found"
    assert row["candidates"] == []
    assert plan["summary"]["bindings"]["not_found"] == 1


# --------------------------------------------------------------------------- #
# dry-run / plan mode
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_dry_run_writes_nothing(tmp_path):
    path = _write_rules(tmp_path, [SIZE_NUMBER, SIZE_SELECT])
    Category.add_root(name="Ручной инструмент", slug="ruchnoy", on_site=True)
    Category.add_root(name="Перчатки и рукавицы", slug="perchatki", on_site=True)

    before = (
        Attribute.objects.count(),
        AttributeOption.objects.count(),
        CategoryAttribute.objects.count(),
    )
    _plan(path)
    after = (
        Attribute.objects.count(),
        AttributeOption.objects.count(),
        CategoryAttribute.objects.count(),
    )
    assert before == after == (0, 0, 0)


@pytest.mark.django_db
def test_plan_structure_and_counts(tmp_path):
    path = _write_rules(tmp_path, [SIZE_NUMBER, SIZE_SELECT])
    Category.add_root(name="Ручной инструмент", slug="ruchnoy", on_site=True)
    Category.add_root(name="Перчатки и рукавицы", slug="perchatki", on_site=True)

    plan = _plan(path)

    assert plan["command"] == "load_attributes"
    assert plan["dry_run"] is True
    assert REQUIRED_ATTRIBUTE_FIELDS <= set(plan["attributes"][0])
    assert plan["summary"]["attributes"] == {"create": 1, "update": 0, "keep": 0}
    assert plan["summary"]["options"] == {"create": 1, "update": 0, "keep": 0}
    assert plan["summary"]["bindings"]["create"] == 2
    assert plan["summary"]["bindings"]["ambiguous"] == 0
    assert plan["summary"]["bindings"]["not_found"] == 0


@pytest.mark.django_db
def test_plan_reports_field_change_before_after(tmp_path):
    """Изменение существующего атрибута печатается как поле + было→станет."""
    Attribute.objects.create(
        slug="size", name="Размер", attribute_type=AttributeType.DECIMAL, unit="см"
    )
    path = _write_rules(tmp_path, [SIZE_NUMBER])
    plan = _plan(path)

    row = next(r for r in plan["attributes"] if r["slug"] == "size")
    assert row["action"] == "update"
    assert {"field": "unit", "from": "см", "to": "мм"} in row["changes"]
    assert row["current"]["unit"] == "см"
    assert row["target"]["unit"] == "мм"


@pytest.mark.django_db
def test_json_report_file(tmp_path):
    path = _write_rules(tmp_path, [SIZE_NUMBER])
    report = tmp_path / "plan.json"

    call_command("load_attributes", "--path", path, "--dry-run", "--json-report", str(report))

    plan = json.loads(report.read_text(encoding="utf-8"))
    assert plan["dry_run"] is True
    assert plan["summary"]["attributes"]["create"] == 1


@pytest.mark.django_db
def test_plan_matches_apply(tmp_path):
    """Эквивалентность: план и боевой прогон принимают одни и те же решения."""
    Category.add_root(name="Ручной инструмент", slug="ruchnoy", on_site=True)
    Category.add_root(name="Перчатки и рукавицы", slug="perchatki", on_site=True)
    path = _write_rules(tmp_path, [SIZE_NUMBER, SIZE_SELECT])

    plan = _plan(path)
    call_command("load_attributes", "--path", path)

    assert Attribute.objects.count() == plan["summary"]["attributes"]["create"]
    assert AttributeOption.objects.count() == plan["summary"]["options"]["create"]
    assert CategoryAttribute.objects.count() == plan["summary"]["bindings"]["create"]

    # Повторный план на уже загруженной схеме — всё keep, писать нечего.
    replan = _plan(path)
    assert replan["summary"]["attributes"] == {"create": 0, "update": 0, "keep": 1}
    assert replan["summary"]["options"] == {"create": 0, "update": 0, "keep": 1}
    assert replan["summary"]["bindings"]["create"] == 0
    assert replan["summary"]["bindings"]["keep"] == 2
