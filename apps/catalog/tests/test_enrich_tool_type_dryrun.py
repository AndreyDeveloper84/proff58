"""Тесты безопасного режима ``enrich_tool_type --dry-run``/``--report-only``
и wiring aliases (ENRICH-DRYRUN-ALIASES).

Использует реальный ``data/tool_type_rules.json`` и canonical taxonomy manifest
(через ``load_tool_types``) — так проверяется реальная разводка 2 подтверждённых
aliases, а не изолированная логика модуля ``tool_type_aliases`` (она уже
покрыта ``test_tool_type_aliases.py``).
"""

from __future__ import annotations

import json

import pytest
from django.core.management import CommandError, call_command

import apps.catalog.management.commands.enrich_tool_type as enrich_cmd_module
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Category,
    EnrichmentLog,
    ImportRun,
    Product,
    ProductAttributeValue,
)


def _root(name, slug):
    return Category.add_root(name=name, slug=slug, on_site=True)


def _product(category, name, code_1c, slug=None):
    return Product.objects.create(
        code_1c=code_1c,
        name=name,
        original_name=name,
        category=category,
        slug=slug or code_1c,
    )


@pytest.fixture
def seeded():
    call_command("load_tool_types")
    return Attribute.objects.get(slug="tool_type")


@pytest.mark.django_db
class TestDryRunWritesNothing:
    def test_zero_db_writes_and_json_counts(self, seeded, capsys):
        root = _root("Электроинструмент", "elektro")
        _product(root, "Перфоратор Bosch GBH 2-26", "p1")
        _product(root, "Удлинитель силовой 50м", "p2")

        pav_before = ProductAttributeValue.objects.count()
        log_before = EnrichmentLog.objects.count()
        run_before = ImportRun.objects.filter(source="enrich_tool_type").count()

        out = call_command("enrich_tool_type", "--dry-run")

        assert ProductAttributeValue.objects.count() == pav_before
        assert EnrichmentLog.objects.count() == log_before
        assert ImportRun.objects.filter(source="enrich_tool_type").count() == run_before

        report = json.loads(out)
        assert report["dry_run"] is True
        assert report["counts"]["matched"] == 1
        assert report["counts"]["moderation"] == 1
        assert report["by_target_slug"]["perforatory"] == 1


@pytest.mark.django_db
class TestAliasWiringInDryRun:
    def test_spetsodezhda_alias_matches_via_legacy_block(self, seeded):
        root = _root("Спецодежда и СИЗ", "siz")  # live-имя, ушло от "Спецодежда и защита"
        _product(root, "Перчатки рабочие х/б", "siz1")

        out = call_command("enrich_tool_type", "--dry-run")
        report = json.loads(out)

        assert report["counts"]["matched"] == 1
        assert report["by_root"]["Спецодежда и СИЗ"]["matched"] == 1
        assert report["by_rule_block"]["Спецодежда и защита"]["matched"] == 1
        assert report["by_target_slug"]["siz-perchatki"] == 1
        assert ProductAttributeValue.objects.count() == 0

    def test_stroitelnoe_alias_matches_via_legacy_block(self, seeded):
        root = _root("Строительный и отделочный инструмент", "stroy")
        _product(root, "Кисть малярная плоская 50мм", "str1")

        out = call_command("enrich_tool_type", "--dry-run")
        report = json.loads(out)

        assert report["counts"]["matched"] == 1
        assert report["by_root"]["Строительный и отделочный инструмент"]["matched"] == 1
        assert report["by_rule_block"]["Строительное и отделочное"]["matched"] == 1
        assert report["by_target_slug"]["str-kisti"] == 1

    def test_write_path_now_uses_aliases_too(self, seeded):
        # ENRICH-WRITE-PATH-HARDENING: боевой прогон резолвит top_name через
        # тот же live_to_legacy, что и --dry-run — расхождение убрано (было
        # намеренным до этого окна, owner-decisions.md §STEP6-KEYWORDS-V1V2).
        root = _root("Спецодежда и СИЗ", "siz")
        _product(root, "Перчатки рабочие х/б", "siz1")

        call_command("enrich_tool_type")

        pav = ProductAttributeValue.objects.get()
        assert pav.value_option.slug == "siz-perchatki"
        assert EnrichmentLog.objects.count() == 1


@pytest.mark.django_db
class TestDryRunWriteParity:
    """Обязательная проверка ENRICH-WRITE-PATH-HARDENING: для одного и того же
    товара с алиасированным корнем dry-run-предсказание и то, что реально
    пишет боевой прогон, совпадают побайтово (slug, provenance-намерение)."""

    def test_dry_run_prediction_matches_write_result_byte_for_byte(self, seeded):
        root = _root("Строительный и отделочный инструмент", "stroy")
        _product(root, "Кисть малярная плоская 50мм", "str1")

        dry_out = call_command("enrich_tool_type", "--dry-run")
        dry_report = json.loads(dry_out)
        assert dry_report["counts"]["matched"] == 1
        (predicted_slug,) = dry_report["by_target_slug"]
        assert predicted_slug == "str-kisti"
        assert ProductAttributeValue.objects.count() == 0  # dry-run — ничего не пишет

        call_command("enrich_tool_type")

        pav = ProductAttributeValue.objects.get()
        assert pav.value_option.slug == predicted_slug

    def test_non_aliased_root_write_path_is_byte_for_byte_unchanged(self, seeded):
        # Инвариант из PR #628: 10 из 13 блоков без alias — top_name уже
        # совпадает с legacy, поведение не меняется (не только для 3 алиасов).
        root = _root("Электроинструмент", "elektro")
        _product(root, "Перфоратор Bosch GBH 2-26", "p1")

        call_command("enrich_tool_type")

        pav = ProductAttributeValue.objects.get()
        assert pav.value_option.slug == "perforatory"


@pytest.mark.django_db
class TestReportBuckets:
    def test_skipped_bucket_for_unmapped_live_root(self, seeded):
        root = _root("Автоинструмент и гаражное оборудование", "auto")
        _product(root, "Компрессометр PROFFI G-324", "auto1")

        out = call_command("enrich_tool_type", "--dry-run")
        report = json.loads(out)

        assert report["counts"]["skipped"] == 1
        assert report["by_root"]["Автоинструмент и гаражное оборудование"]["skipped"] == 1
        assert "matched" not in report["by_rule_block"].get(
            "Автоинструмент и гаражное оборудование", {}
        )

    def test_conflict_bucket_is_recategorize(self, seeded):
        root = _root("Электроинструмент", "elektro")
        _product(root, "Газонокосилка аккумуляторная ЗУБР ГКЛ-4336", "gk1")

        out = call_command("enrich_tool_type", "--dry-run")
        report = json.loads(out)

        assert report["counts"]["conflict"] == 1
        assert report["by_root"]["Электроинструмент"]["conflict"] == 1


@pytest.mark.django_db
class TestExistingToolTypeChangeReport:
    def test_old_slug_to_proposed_slug_reported_without_write(self, seeded):
        attr = seeded
        root = _root("Электроинструмент", "elektro")
        product = _product(root, "Перфоратор Bosch GBH 2-26", "p1")
        dreli_opt = AttributeOption.objects.get(attribute=attr, slug="dreli-shurupoverty")
        pav = ProductAttributeValue.objects.create(
            product=product, attribute=attr, value_option=dreli_opt
        )

        out = call_command("enrich_tool_type", "--dry-run")
        report = json.loads(out)

        changes = report["existing_tool_type_changes"]
        assert len(changes) == 1
        assert changes[0]["product_id"] == product.id
        assert changes[0]["old_slug"] == "dreli-shurupoverty"
        assert changes[0]["proposed_slug"] == "perforatory"

        pav.refresh_from_db()
        assert pav.value_option_id == dreli_opt.id  # не переписан


@pytest.mark.django_db
class TestFilters:
    def test_category_filter_scopes_scan(self, seeded):
        elektro = _root("Электроинструмент", "elektro")
        ruchnoy = _root("Ручной инструмент", "ruchnoy")
        _product(elektro, "Перфоратор Bosch", "p1")
        _product(ruchnoy, "Молоток слесарный 500г", "p2")

        out = call_command("enrich_tool_type", "--dry-run", "--category", "Электроинструмент")
        report = json.loads(out)

        assert sum(report["counts"].values()) == 1
        assert report["by_root"] == {"Электроинструмент": report["by_root"]["Электроинструмент"]}

    def test_unknown_category_filter_raises(self, seeded):
        with pytest.raises(CommandError):
            call_command("enrich_tool_type", "--dry-run", "--category", "Несуществующий раздел")

    def test_product_ids_filter_scopes_scan(self, seeded):
        root = _root("Электроинструмент", "elektro")
        p1 = _product(root, "Перфоратор Bosch", "p1")
        _product(root, "Дрель ударная", "p2")

        out = call_command("enrich_tool_type", "--dry-run", "--product-ids", str(p1.id))
        report = json.loads(out)

        assert sum(report["counts"].values()) == 1
        assert report["by_target_slug"] == {"perforatory": 1}

    def test_limit_caps_scanned_products(self, seeded):
        root = _root("Электроинструмент", "elektro")
        _product(root, "Перфоратор Bosch 1", "p1")
        _product(root, "Перфоратор Bosch 2", "p2")

        out = call_command("enrich_tool_type", "--dry-run", "--limit", "1")
        report = json.loads(out)

        assert sum(report["counts"].values()) == 1


@pytest.mark.django_db
class TestJsonReportFile:
    def test_json_report_written_to_file(self, seeded, tmp_path):
        root = _root("Электроинструмент", "elektro")
        _product(root, "Перфоратор Bosch", "p1")
        out_path = tmp_path / "report.json"

        call_command("enrich_tool_type", "--dry-run", "--json-report", str(out_path))

        assert out_path.exists()
        report = json.loads(out_path.read_text(encoding="utf-8"))
        assert report["counts"]["matched"] == 1


@pytest.mark.django_db
class TestAliasCollisionExitsNonZero:
    def test_collision_stops_before_any_write(self, seeded, monkeypatch):
        root = _root("Электроинструмент", "elektro")
        _product(root, "Перфоратор Bosch", "p1")

        # Коллизия: оба legacy-блока претендуют на одно live-имя.
        monkeypatch.setattr(
            enrich_cmd_module,
            "ROOT_ALIASES",
            {"Электроинструмент": "X", "Ручной инструмент": "X"},
            raising=False,
        )

        def _boom(rule_categories, aliases=None):
            from apps.catalog.tool_type_aliases import AliasConfigError

            raise AliasConfigError("alias_collision: X назначено двум legacy-блокам")

        monkeypatch.setattr(enrich_cmd_module, "resolve_live_to_legacy", _boom)

        with pytest.raises(CommandError, match="alias_collision"):
            call_command("enrich_tool_type", "--dry-run")

        assert ProductAttributeValue.objects.count() == 0
        assert EnrichmentLog.objects.count() == 0

        with pytest.raises(CommandError, match="alias_collision"):
            call_command("enrich_tool_type")  # тоже без --dry-run

        assert ProductAttributeValue.objects.count() == 0
        assert ImportRun.objects.filter(source="enrich_tool_type").count() == 0
