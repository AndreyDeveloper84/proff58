"""Preflight-валидация option slug в load_tool_types (DEVIATION-2)."""

import json
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import Attribute, AttributeOption, AttributeType


def _rules_file(tmp_path, rules):
    payload = {
        "categories": [
            {"category": "Ручной инструмент", "extraction": "priority_keyword", "rules": rules}
        ]
    }
    path = tmp_path / "tool_type_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.mark.django_db
def test_duplicate_slugs_in_seed_rejected(tmp_path):
    """Один slug у двух разных значений в seed — импорт запрещён."""
    base = _rules_file(
        tmp_path,
        [
            {"tool_type": "Степлеры и заклёпочники", "slug": "steplery"},
            {"tool_type": "Степлеры (скобозабивные)", "slug": "steplery"},
        ],
    )
    with pytest.raises(CommandError, match="duplicate option slugs in seed"):
        call_command("load_tool_types", path=str(base))


@pytest.mark.django_db
def test_same_value_slug_repeat_in_seed_allowed(tmp_path):
    """Повтор пары (value, slug) в нескольких категориях — легален (дедуп по value)."""
    base = _rules_file(
        tmp_path,
        [
            {"tool_type": "Зарядные устройства", "slug": "zaryadnye"},
            {"tool_type": "Зарядные устройства", "slug": "zaryadnye"},
        ],
    )
    call_command("load_tool_types", path=str(base))
    assert AttributeOption.objects.count() == 1


@pytest.mark.django_db
def test_duplicate_slug_already_in_db_rejected(tmp_path):
    """В БД уже >1 записи на slug (состояние до констрейнта) — импорт запрещён.

    Дубль в тестовой БД через ORM не создать (констрейнт миграции 0027),
    поэтому выборка мокается — проверяется именно логика multiplicity guard.
    """
    Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    base = _rules_file(
        tmp_path,
        [{"tool_type": "Степлеры (скобозабивные)", "slug": "steplery"}],
    )
    fake_rows = [
        ("steplery", "Степлеры и заклёпочники"),
        ("steplery", "Степлеры (скобозабивные)"),
    ]
    qs = Mock()
    qs.values_list.return_value = fake_rows
    with patch.object(AttributeOption.objects, "filter", return_value=qs):
        with pytest.raises(CommandError, match="duplicate option slugs in DB"):
            call_command("load_tool_types", path=str(base))


@pytest.mark.django_db
def test_slug_value_conflict_with_db_rejected(tmp_path):
    """Одна DB-запись на slug, но с другим value — импорт запрещён."""
    attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=attr, value="Степлеры (скобозабивные)", slug="steplery")
    base = _rules_file(
        tmp_path,
        [{"tool_type": "Степлеры и заклёпочники", "slug": "steplery"}],
    )
    with pytest.raises(CommandError, match="option slug conflicts with DB"):
        call_command("load_tool_types", path=str(base))


@pytest.mark.django_db
def test_valid_seed_passes(tmp_path):
    base = _rules_file(
        tmp_path,
        [
            {"tool_type": "Степлеры и заклёпочники", "slug": "steplery-i-zaklepochniki"},
            {"tool_type": "Степлеры (скобозабивные)", "slug": "steplery"},
        ],
    )
    call_command("load_tool_types", path=str(base))
    assert AttributeOption.objects.count() == 2
