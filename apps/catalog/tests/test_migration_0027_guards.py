"""Guard-сценарии миграции 0027 (DEVIATION-2): no-op / idempotent / RuntimeError."""

import importlib.util
from pathlib import Path

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.catalog.models import Attribute, AttributeOption, AttributeType

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "0027_reslug_steplery_unique_option_slug.py"
)
_spec = importlib.util.spec_from_file_location("migration_0027", _MIGRATION_PATH)
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)


def _attr(slug="tool_type"):
    return Attribute.objects.create(slug=slug, name="T", attribute_type=AttributeType.SELECT)


def _option(pk, attribute, value, slug):
    return AttributeOption.objects.create(pk=pk, attribute=attribute, value=value, slug=slug)


@pytest.fixture
def relaxed_slug_constraint(db):
    """Временно снимает uniq (attribute, slug) для непустых slug.

    Историческое состояние DEVIATION-2 (id=16 и id=73 со slug='steplery' на одном
    атрибуте) нарушает констрейнт и не может быть создано в мигрированной тестовой БД.
    """
    constraint = next(
        c
        for c in AttributeOption._meta.constraints
        if c.name == "uniq_attributeoption_attr_slug_nonempty"
    )
    with connection.schema_editor() as editor:
        editor.remove_constraint(AttributeOption, constraint)
    try:
        yield
    finally:
        # В транзакционных тестах проверки constraints отложены до конца транзакции;
        # перед CREATE UNIQUE INDEX нужно сбросить накопленные trigger events.
        connection.check_constraints()
        with connection.schema_editor() as editor:
            editor.add_constraint(AttributeOption, constraint)


@pytest.mark.django_db
def test_reslug_noop_without_option_16():
    _attr()
    _mig.reslug_forward(global_apps, None)  # нет id=16 — no-op
    assert AttributeOption.objects.count() == 0


@pytest.mark.django_db
def test_reslug_noop_when_already_applied():
    _option(16, _attr(), "Степлеры и заклёпочники", "steplery-i-zaklepochniki")
    _mig.reslug_forward(global_apps, None)
    assert AttributeOption.objects.get(pk=16).slug == "steplery-i-zaklepochniki"


@pytest.mark.django_db
def test_reslug_raises_when_new_slug_but_wrong_value():
    """NEW_SLUG при чужом value — повреждённое состояние, а не идемпотентность."""
    _option(16, _attr(), "Другое значение", "steplery-i-zaklepochniki")
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)


@pytest.mark.django_db
def test_reslug_raises_when_option_16_in_wrong_attribute():
    _option(16, _attr(slug="ne_tool_type"), "Степлеры и заклёпочники", "steplery")
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)


@pytest.mark.django_db
def test_reslug_happy_path(relaxed_slug_constraint):
    attr = _attr()
    _option(16, attr, "Степлеры и заклёпочники", "steplery")
    _option(73, attr, "Степлеры (скобозабивные)", "steplery")
    _mig.reslug_forward(global_apps, None)
    assert AttributeOption.objects.get(pk=16).slug == "steplery-i-zaklepochniki"
    assert AttributeOption.objects.get(pk=73).slug == "steplery"  # канон не тронут


@pytest.mark.django_db
def test_reslug_raises_without_canonical_option_73():
    _option(16, _attr(), "Степлеры и заклёпочники", "steplery")
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)


@pytest.mark.django_db
def test_reslug_raises_when_canonical_73_unexpected_state():
    attr = _attr()
    _option(16, attr, "Степлеры и заклёпочники", "steplery")
    _option(73, attr, "Неожиданное значение", "steplery-73")
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)


@pytest.mark.django_db
def test_reslug_guard_raises_on_unexpected_state():
    _option(16, _attr(), "Другое значение", "steplery")
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)
