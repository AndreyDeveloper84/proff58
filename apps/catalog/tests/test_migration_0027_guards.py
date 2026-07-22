"""Guard-сценарии миграции 0027 (DEVIATION-2): no-op / idempotent / RuntimeError."""

import importlib.util
from pathlib import Path

import pytest
from django.apps import apps as global_apps

from apps.catalog.models import Attribute, AttributeOption, AttributeType

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "0027_reslug_steplery_unique_option_slug.py"
)
_spec = importlib.util.spec_from_file_location("migration_0027", _MIGRATION_PATH)
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)


def _attr():
    return Attribute.objects.create(
        slug="tool_type", name="T", attribute_type=AttributeType.SELECT
    )


@pytest.mark.django_db
def test_reslug_noop_without_option_16():
    _attr()
    _mig.reslug_forward(global_apps, None)  # нет id=16 — no-op
    assert AttributeOption.objects.count() == 0


@pytest.mark.django_db
def test_reslug_noop_when_already_applied():
    AttributeOption.objects.create(
        pk=16,
        attribute=_attr(),
        value="Степлеры и заклёпочники",
        slug="steplery-i-zaklepochniki",
    )
    _mig.reslug_forward(global_apps, None)
    assert AttributeOption.objects.get(pk=16).slug == "steplery-i-zaklepochniki"


@pytest.mark.django_db
def test_reslug_happy_path():
    AttributeOption.objects.create(
        pk=16, attribute=_attr(), value="Степлеры и заклёпочники", slug="steplery"
    )
    _mig.reslug_forward(global_apps, None)
    assert AttributeOption.objects.get(pk=16).slug == "steplery-i-zaklepochniki"


@pytest.mark.django_db
def test_reslug_guard_raises_on_unexpected_state():
    AttributeOption.objects.create(
        pk=16, attribute=_attr(), value="Другое значение", slug="steplery"
    )
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)
