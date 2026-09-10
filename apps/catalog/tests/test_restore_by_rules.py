"""Достройка обрезанных названий по правилам (catalog_restore_by_rules).

Правило работает сразу по сотням позиций, поэтому проверок на отказ здесь
больше, чем на успех: одна ошибочная регулярка испортит всю серию разом.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.catalog.models import Product

FULL = "Плашка М 6х0,5 класс точности 6g, сталь 9ХС, ГОСТ 9740-71"
CUT_RAW = FULL[:50]


@pytest.fixture
def cut(db):
    return Product.objects.create(
        name=CUT_RAW.strip(), original_name=CUT_RAW, slug="plashka-6", article="P-6"
    )


@pytest.mark.django_db
def test_rule_completes_the_series(cut):
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == FULL
    assert cut.content_field_sources["name"] == "rules"


@pytest.mark.django_db
def test_dry_run_writes_nothing(cut):
    before = cut.name
    call_command("catalog_restore_by_rules", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == before


@pytest.mark.django_db
def test_untouched_names_are_not_rewritten(db):
    """Правило работает только по обрезанным: у остальных хвост не терялся."""
    whole = Product.objects.create(
        name="Плашка М 8х1,0 класс точности 6g, сталь 9ХС",
        original_name="Плашка М 8х1,0 класс точности 6g, сталь 9ХС",  # не 50 символов
        slug="plashka-8",
        article="P-8",
    )
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    whole.refresh_from_db()
    assert whole.name == "Плашка М 8х1,0 класс точности 6g, сталь 9ХС"


@pytest.mark.django_db
def test_name_from_web_is_not_overwritten(cut):
    """Найденное в карточке производителя правило поверх не кладёт."""
    cut.name = "Плашка М 6х0,5, из карточки производителя"
    cut.content_field_sources = {"name": "web"}
    cut.save()
    call_command("catalog_restore_by_rules", "--commit", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == "Плашка М 6х0,5, из карточки производителя"


@pytest.mark.django_db
def test_single_rule_can_be_selected(cut, tmp_path):
    call_command("catalog_restore_by_rules", "--rule=sverlo-cx-sred-gost10902", verbosity=0)
    cut.refresh_from_db()
    assert cut.name == CUT_RAW.strip()  # плашку это правило не трогает


def test_every_rule_has_justification():
    """Без обоснования правило принимать нельзя: оно правит сотни карточек разом."""
    data = json.loads(
        (Path(settings.BASE_DIR) / "data" / "name_restore_rules.json").read_text(encoding="utf-8")
    )
    for rule in data["rules"]:
        assert rule.get("note"), f"{rule['id']}: нет пояснения, откуда взят хвост"
        assert 0 < float(rule["confidence"]) <= 1
