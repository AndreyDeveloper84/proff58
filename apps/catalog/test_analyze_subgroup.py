"""Смоук-тест аналитического тулкита analyze_subgroup (характеризация каталога)."""

from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command

from apps.catalog.management.commands.analyze_subgroup import names_for_subgroup


def test_names_for_subgroup_finds_products():
    names = names_for_subgroup("Буры")
    assert len(names) > 100  # подгруппа «Буры» крупная
    assert any("бур" in n.lower() for n in names)


def test_command_composition_and_spec(tmp_path):
    spec = {
        "core_words": ["бур", "буры", "яябур"],
        "splits": {"nabory-burov": ["набор буров"]},
        "attributes": {
            "shank_type": {
                "kind": "select",
                "options": {"sds-plus": ["sds-plus", "sds+"], "sds-max": ["sds-max"]},
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    out = StringIO()
    call_command(
        "analyze_subgroup", "Буры", "--spec", str(spec_path), "--examples", "2", stdout=out
    )
    report = out.getvalue()

    assert "Подгруппа «Буры»" in report
    assert "состав" in report
    assert "сплит подтипов" in report
    assert "shank_type" in report
    assert "sds-plus" in report


def test_command_batch(tmp_path):
    batch = {
        "Буры": {"core_words": ["бур"], "splits": {"nabory-burov": ["набор буров"]}},
        "Коронки": {"core_words": ["коронка"], "attributes": {}},
    }
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    out = StringIO()
    call_command("analyze_subgroup", "--batch", str(batch_path), stdout=out)
    report = out.getvalue()
    assert "Подгруппа «Буры»" in report
    assert "Подгруппа «Коронки»" in report


def test_survey_catalog_prioritised_table():
    out = StringIO()
    call_command("survey_catalog", "--min", "100", "--top", "30", stdout=out)
    report = out.getvalue()
    assert "подгруппа" in report
    assert "Сверла" in report  # крупная подгруппа должна попасть в обзор
    assert "%" in report
