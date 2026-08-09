"""ХАР-PRE: dry-run/plan ``load_attributes`` + дефекты загрузчика схемы.

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

Окно ХАР-BIND (задание владельца 2026-08-09) добавило четвёртый:

4. **Дефект «привязка в мёртвый узел»** — лестница разрешала имя, но не проверяла,
   что выбранный узел живой: единственный кандидат с ``is_active=False`` /
   ``on_site=False`` принимался молча, привязка создавалась, а атрибут не попадал
   в фасеты витрины (на живых потомках его нет, а сам узел скрыт). Инвариант:
   такая привязка получает отдельный статус ``dead_category`` и код причины
   ``bound:*:dead``, по умолчанию — WARNING с указанием выбранного узла,
   ``--strict-live-categories`` делает её фатальной.

Плюс сам dry-run: ничего не пишет, печатает machine-readable план
(create/update/keep + было→станет) и совпадает с тем, что реально делает apply.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.ingest import data_dir
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
# Дефект 4 (ХАР-BIND): привязка уходила в мёртвый узел молча
# --------------------------------------------------------------------------- #


def _dead_leaf() -> tuple[Category, Category]:
    """Живой раздел и мёртвый лист под ним — ровно случай «Метчики и плашки» (40).

    Глубины как на стенде: корень depth=1, «Металлорежущий инструмент» depth=2,
    «Метчики и плашки» depth=3 — поэтому лестница работает уровнем ``tree``, не ``top``.
    """
    root = Category.add_root(name="Инструмент", slug="instrument", is_active=True, on_site=True)
    section = root.add_child(
        name="Металлорежущий инструмент", slug="metallorezhushchiy", is_active=True, on_site=True
    )
    dead = section.add_child(
        name="Метчики и плашки", slug="metchiki-i-plashki", is_active=False, on_site=False
    )
    return section, dead


TAPS = {
    "tool_type": "metchiki-plashki",
    "category": "Метчики и плашки",
    "attributes": [{"slug": "tool_kind", "name": "Вид", "kind": "select", "options": []}],
}
TAPS_LIVE = dict(TAPS, category="Металлорежущий инструмент")


@pytest.mark.django_db
def test_plan_marks_binding_to_dead_category(tmp_path):
    """Дефект 4: единственный кандидат мёртв — это отдельный статус, а не «bound»."""
    _section, dead = _dead_leaf()
    path = _write_rules(tmp_path, [TAPS])
    plan = _plan(path)

    row = next(r for r in plan["bindings"] if r["attribute"] == "tool_kind")
    assert row["status"] == "dead_category"
    assert row["reason"] == "bound:tree:dead"
    assert row["category_id"] == dead.pk
    assert plan["summary"]["bindings"]["dead_category"] == 1
    assert plan["summary"]["bindings"]["bound"] == 0


@pytest.mark.django_db
def test_plan_prints_dead_binding_separately_with_chosen_node(tmp_path):
    """План печатает такие привязки отдельно: какой узел выбран и почему."""
    _section, dead = _dead_leaf()
    path = _write_rules(tmp_path, [TAPS])

    err = StringIO()
    call_command("load_attributes", "--path", path, "--dry-run", stdout=StringIO(), stderr=err)
    human = err.getvalue()

    assert "dead_category 1" in human
    assert f"#{dead.pk} metchiki-i-plashki" in human
    assert "bound:tree:dead" in human
    assert "active=False" in human and "on_site=False" in human


@pytest.mark.django_db
def test_dead_category_binding_is_warning_by_default(tmp_path):
    """По умолчанию не фатально: привязка создаётся как раньше, но с предупреждением."""
    _section, dead = _dead_leaf()
    path = _write_rules(tmp_path, [TAPS])

    err = StringIO()
    call_command("load_attributes", "--path", path, stderr=err)

    assert CategoryAttribute.objects.filter(category=dead, attribute__slug="tool_kind").exists()
    assert "bound:tree:dead" in err.getvalue()


@pytest.mark.django_db
def test_dead_category_binding_is_fatal_under_strict_live_categories(tmp_path):
    """Фатальность включается явным флагом — как ``--strict-bindings`` для not_found."""
    _section, _dead = _dead_leaf()
    path = _write_rules(tmp_path, [TAPS])

    with pytest.raises(CommandError) as exc:
        call_command("load_attributes", "--path", path, "--strict-live-categories")

    assert "Метчики и плашки" in str(exc.value)
    assert not Attribute.objects.filter(slug="tool_kind").exists()
    assert not CategoryAttribute.objects.exists()


@pytest.mark.django_db
def test_live_binding_is_not_flagged_as_dead(tmp_path):
    """Живой узел guard не трогает: статус «bound», счётчик мёртвых нулевой."""
    section, _dead = _dead_leaf()
    path = _write_rules(tmp_path, [TAPS_LIVE])
    plan = _plan(path)

    row = next(r for r in plan["bindings"] if r["attribute"] == "tool_kind")
    assert row["status"] == "bound"
    assert row["reason"] == "bound:tree"
    assert row["category_id"] == section.pk
    assert plan["summary"]["bindings"]["dead_category"] == 0


@pytest.mark.django_db
def test_dead_candidate_dropped_in_favour_of_live_is_not_flagged(tmp_path):
    """Мёртвый однофамилец рядом с живым — это «bound:top:live», а не dead_category."""
    _legacy, live = _two_roots_same_name()
    path = _write_rules(tmp_path, [HAND_TOOL])
    plan = _plan(path)

    row = next(r for r in plan["bindings"] if r["attribute"] == "size")
    assert row["status"] == "bound"
    assert row["reason"] == "bound:top:live"
    assert row["category_id"] == live.pk
    assert plan["summary"]["bindings"]["dead_category"] == 0


@pytest.mark.django_db
def test_real_rules_bind_taps_to_live_metal_cutting_section():
    """ХАР-BIND: боевой словарь ведёт метчики/плашки в живой раздел, а не в мёртвый лист."""
    section, dead = _dead_leaf()
    section.add_child(name="Метчики", slug="metchiki", is_active=True, on_site=True)
    section.add_child(name="Плашки", slug="plashki", is_active=True, on_site=True)

    plan = _plan(str(data_dir()))
    taps = [r for r in plan["bindings"] if r["tool_type"] == "metchiki-plashki"]

    assert taps, "блок metchiki-plashki исчез из словаря"
    assert {r["category"] for r in taps} == {"Металлорежущий инструмент"}
    assert {r["category_id"] for r in taps} == {section.pk}
    assert {r["status"] for r in taps} == {"bound"}
    # tool_kind — тот самый атрибут, которого из-за мёртвой 40 не было в фасетах.
    assert "tool_kind" in {r["attribute"] for r in taps}

    call_command("load_attributes")
    bound = set(
        CategoryAttribute.objects.filter(category=section).values_list("attribute__slug", flat=True)
    )
    assert "tool_kind" in bound
    assert not CategoryAttribute.objects.filter(category=dead).exists()


# --------------------------------------------------------------------------- #
# ХАР-BIND-03: две последние мёртвые цели в боевом словаре
# --------------------------------------------------------------------------- #


def _bolts_and_sets_tree() -> tuple[Category, Category]:
    """Стенд в миниатюре: мёртвые «Болты и винты» / «Наборы инструмента» + живые цели.

    Соответствие узлам стенда: 29→31 (оба мёртвые) против живой пары 355→358
    «Крепёж и метизы»→«Болты»; легаси-корень 1→45 (мёртвая) против живой пары
    339→340 «Ручной инструмент»→«Наборы ручного инструмента».
    """
    legacy = Category.add_root(
        name="Каталог (легаси)", slug="legacy-root", is_active=False, on_site=False
    )
    dead_fasteners = legacy.add_child(
        name="Крепёж (легаси)", slug="krepezh-legacy", is_active=False, on_site=False
    )
    dead_fasteners.add_child(
        name="Болты и винты", slug="bolty-i-vinty", is_active=False, on_site=False
    )
    legacy.add_child(
        name="Наборы инструмента", slug="nabory-instrumenta", is_active=False, on_site=False
    )

    fasteners = Category.add_root(
        name="Крепёж и метизы", slug="krepezh-i-metizy", is_active=True, on_site=True
    )
    bolts = fasteners.add_child(name="Болты", slug="krepezh-bolty", is_active=True, on_site=True)
    hand = Category.add_root(name="Ручной инструмент", slug="ruchnoy", is_active=True, on_site=True)
    sets = hand.add_child(
        name="Наборы ручного инструмента",
        slug="nabory-ruchnogo-instrumenta",
        is_active=True,
        on_site=True,
    )
    return bolts, sets


@pytest.mark.django_db
def test_real_rules_bind_bolts_and_sets_to_live_nodes():
    """ХАР-BIND-03: боевой словарь ведёт крепёж и наборы в живые узлы витрины."""
    bolts, sets = _bolts_and_sets_tree()

    plan = _plan(str(data_dir()), "--allow-ambiguous")

    rows = {
        "krep-bolty": [r for r in plan["bindings"] if r["tool_type"] == "krep-bolty"],
        "nabory-instrumenta": [
            r for r in plan["bindings"] if r["tool_type"] == "nabory-instrumenta"
        ],
    }
    assert rows["krep-bolty"], "блок krep-bolty исчез из словаря"
    assert rows["nabory-instrumenta"], "блок nabory-instrumenta исчез из словаря"

    assert {r["category"] for r in rows["krep-bolty"]} == {"Болты"}
    assert {r["category_id"] for r in rows["krep-bolty"]} == {bolts.pk}
    assert {r["status"] for r in rows["krep-bolty"]} == {"bound"}

    assert {r["category"] for r in rows["nabory-instrumenta"]} == {"Наборы ручного инструмента"}
    assert {r["category_id"] for r in rows["nabory-instrumenta"]} == {sets.pk}
    assert {r["status"] for r in rows["nabory-instrumenta"]} == {"bound"}


@pytest.mark.django_db
def test_real_rules_have_no_dead_bindings_left():
    """Критерий разблокировки: строгий режим на полном словаре больше не падает."""
    _bolts_and_sets_tree()

    plan = _plan(str(data_dir()), "--allow-ambiguous")
    dead = [r["category"] for r in plan["bindings"] if r["status"] == "dead_category"]

    assert dead == []
    assert plan["summary"]["bindings"]["dead_category"] == 0


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
