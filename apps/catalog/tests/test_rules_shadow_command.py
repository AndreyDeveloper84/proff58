import hashlib
import json
import os
import re
import stat
import uuid
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.models import ContentFinding
from apps.catalog.management.commands.catalog_rules_shadow import VOLATILE_REPORT_KEYS
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogProcessingItem,
    CatalogProcessingRun,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)
from apps.catalog.processing import canonical_hash
from apps.catalog.rules_engine import load_corpus, validate_gate_sample


def _category():
    return Category.add_root(name=f"Кат-{uuid.uuid4().hex[:8]}", slug=f"cat-{uuid.uuid4().hex[:8]}")


def _product(**kw):
    defaults = dict(
        category=_category(),
        name="",
        slug=f"p-{uuid.uuid4().hex[:8]}",
        original_name="",
        status=ProductStatus.IMPORTED,
        is_active=True,
        article="A1",
        source_group="Крепёж",
        content_locked=False,
        available_quantity=1,
        price="100",
    )
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _tool_type_attr():
    return Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )[0]


def _option(attr, value, slug):
    return AttributeOption.objects.get_or_create(
        attribute=attr, value=value, defaults={"slug": slug}
    )[0]


def _ruleset_file(tmp_path, slug="krep-shplinty", rules=None, fixtures=None):
    if rules is None:
        rules = [
            {
                "rule_ref": "tt-test-001",
                "option_slug": slug,
                "match": {
                    "original_name_keywords_any": ["шплинт"],
                    "source_group_any": ["Крепёж"],
                },
                "derived_from": [26864, 26865],
            }
        ]
    if fixtures is None:
        fixtures = [
            {
                "fixture_ref": "nf-test-001",
                "rule_refs": ["tt-test-001"],
                "name": "Пассатижи комбинированные",
            }
        ]
    data = {
        "version": 1,
        "ruleset_id": "tool_type.v1",
        "rules": rules,
        "negative_fixtures": fixtures,
    }
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _two_rule_ruleset(tmp_path, prefix="col"):
    """Два candidate-правила с РАЗНЫМИ slugs: оба матчат «Шплинт оцинкованный …»."""
    rules = [
        {
            "rule_ref": f"tt-{prefix}-001",
            "option_slug": "krep-shplinty",
            "match": {
                "original_name_keywords_any": ["шплинт"],
                "source_group_any": ["Крепёж"],
            },
            "derived_from": [101, 102],
        },
        {
            "rule_ref": f"tt-{prefix}-002",
            "option_slug": "krep-gvozdi",
            "match": {
                "original_name_keywords_any": ["оцинк"],
                "source_group_any": ["Крепёж"],
            },
            "derived_from": [103, 104],
        },
    ]
    fixtures = [
        {"fixture_ref": f"nf-{prefix}-001", "rule_refs": [f"tt-{prefix}-001"], "name": "Пассатижи"},
        {"fixture_ref": f"nf-{prefix}-002", "rule_refs": [f"tt-{prefix}-002"], "name": "Молоток"},
    ]
    return _ruleset_file(tmp_path, rules=rules, fixtures=fixtures)


def _corpus_file(tmp_path, product_ids, applied_slug="krep-shplinty", original_names=None):
    items = []
    for i, pid in enumerate(product_ids):
        facts = {
            "name": "",
            "original_name": original_names[i] if original_names else f"Товар {pid}",
            "brand": "",
            "source_group": "Крепёж",
            "article": f"C{pid}",
        }
        items.append(
            {
                "product_id": pid,
                "change_id": f"ch-{pid}",
                "pav_id": 5000 + pid,
                "applied_option_slug": applied_slug,
                "facts_hash": canonical_hash(facts),
                **facts,
            }
        )
    data = {
        "version": 1,
        "corpus_id": "applied-tool-type.test",
        "counters": {
            "raw_applied_changes": len(items),
            "distinct_products": len(items),
            "current_label_corpus": len(items),
            "historical_label_collisions": 0,
        },
        "items": items,
    }
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _db_counts():
    return (
        Product.objects.count(),
        ProductAttributeValue.objects.count(),
        CatalogChange.objects.count(),
        CatalogProcessingRun.objects.count(),
        CatalogProcessingItem.objects.count(),
        ContentFinding.objects.count(),
    )


def _run(ruleset, out, **kw):
    args = {"ruleset": str(ruleset), "pool": "in-stock", "out": str(out)}
    args.update(kw)
    call_command("catalog_rules_shadow", **args)
    return json.loads(out.read_text(encoding="utf-8"))


# --- report v1.0: versioning / snapshot / universe ---


@pytest.mark.django_db
def test_report_versioning_fields(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт 6,4х76 оцинкованный", article="A2")
    out = tmp_path / "report.json"
    buf = StringIO()
    call_command(
        "catalog_rules_shadow",
        ruleset=str(_ruleset_file(tmp_path)),
        pool="in-stock",
        out=str(out),
        sample_size=5,
        seed=42,
        stdout=buf,
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["report_schema_version"] == "1.0"
    assert report["matcher_version"] == "1.0"
    assert isinstance(report["code_sha"], str) and report["code_sha"]
    assert report["pool_filter_version"] == "1.0"
    assert report["ruleset_id"] == "tool_type.v1"
    assert len(report["ruleset_hash"]) == 64
    assert len(report["taxonomy_hash"]) == 64
    assert report["command"]["name"] == "catalog_rules_shadow"
    assert report["command"]["args"]["pool"] == "in-stock"
    assert report["command"]["args"]["seed"] == 42
    assert report["started_at"] and report["finished_at"]
    assert report["duration_seconds"] >= 0
    assert report["snapshot_isolation"]  # фактический режим зафиксирован, непустой
    assert len(report["input_universe_hash"]) == 64
    pool = report["pool"]
    assert pool["rewrite_attempts"] == 0
    assert "typed_eligible_universe" in pool
    assert "excluded_existing_tool_type" in pool
    # stdout: sha256 файла + content_hash (canonical_hash без volatile-полей)
    assert "sha256=" in buf.getvalue()
    assert "content_hash=" in buf.getvalue()


@pytest.mark.django_db
def test_typed_eligible_universe_published(tmp_path):
    attr = _tool_type_attr()
    opt = _option(attr, "Шплинты", "krep-shplinty")
    typed = _product(original_name="Шплинт 6,4х76", article="A4")
    ProductAttributeValue.objects.create(
        product=typed, attribute=attr, value_option=opt, source=Source.WEB, confidence=85
    )
    untyped = _product(original_name="Шплинт 3,2х50", article="A5")
    report = _run(_ruleset_file(tmp_path), tmp_path / "report.json")
    assert report["pool"]["size"] == 1  # typed товар в пул untyped не входит
    assert report["pool"]["typed_eligible_universe"] == 1
    assert report["pool"]["excluded_existing_tool_type"] == 1
    assert report["counts"]["excluded_existing_tool_type"] == 1
    ids = [p["product_id"] for p in report["predictions"]]
    assert typed.pk not in ids  # перезапись запрещена: товар даже не оценивается
    assert untyped.pk in ids


@pytest.mark.django_db
def test_whitespace_article_excluded(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    ws = _product(original_name="Шплинт 6,4х76 оцинкованный", article="   ")
    ok = _product(original_name="Шплинт 3,2х50", article="A6")
    report = _run(_ruleset_file(tmp_path), tmp_path / "report.json")
    assert report["pool"]["size"] == 1
    ids = [p["product_id"] for p in report["predictions"]]
    assert ws.pk not in ids
    assert ok.pk in ids


@pytest.mark.django_db
def test_inactive_locked_out_of_stock_excluded(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    inactive = _product(original_name="Шплинт неактивный", article="B1", is_active=False)
    locked = _product(original_name="Шплинт залоченный", article="B2", content_locked=True)
    oos = _product(original_name="Шплинт без остатка", article="B3", available_quantity=0)
    ok = _product(original_name="Шплинт обычный", article="B4")
    ruleset = _ruleset_file(tmp_path)
    for pool_name in ("in-stock", "all"):
        report = _run(ruleset, tmp_path / f"report-{pool_name}.json", pool=pool_name)
        ids = {p["product_id"] for p in report["predictions"]}
        assert ok.pk in ids
        assert inactive.pk not in ids  # inactive исключён из обоих пулов
        assert locked.pk not in ids  # locked исключён из обоих пулов
        if pool_name == "in-stock":
            assert oos.pk not in ids  # out-of-stock исключён из in-stock
            assert report["pool"]["size"] == 1
        else:
            assert oos.pk in ids  # …но присутствует в all
            assert report["pool"]["size"] == 2


@pytest.mark.django_db
def test_pool_all_vs_in_stock(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт со склада", article="C1")
    _product(original_name="Шплинт без остатка", article="C2", available_quantity=0)
    ruleset = _ruleset_file(tmp_path)
    sizes = {}
    for pool_name in ("in-stock", "all"):
        report = _run(ruleset, tmp_path / f"{pool_name}.json", pool=pool_name)
        assert report["pool"]["name"] == pool_name
        sizes[pool_name] = report["pool"]["size"]
    assert sizes["in-stock"] == 1
    assert sizes["all"] == 2


# --- atomic output / versioning файла ---


@pytest.mark.django_db
def test_unique_default_filename_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.management.commands.catalog_rules_shadow.DEFAULT_OUT_DIR",
        tmp_path / "shadow",
    )
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт 6,4х76", article="E1")
    ruleset = _ruleset_file(tmp_path)
    for _ in range(2):
        call_command("catalog_rules_shadow", ruleset=str(ruleset), pool="in-stock")
    files = sorted((tmp_path / "shadow").glob("rules_shadow_*.json"))
    assert len(files) == 2  # два прогона → два разных файла, оба существуют
    assert files[0].name != files[1].name
    for f in files:
        assert json.loads(f.read_text(encoding="utf-8"))["report_schema_version"] == "1.0"


@pytest.mark.django_db
def test_out_exists_requires_force(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт 6,4х76", article="D1")
    ruleset = _ruleset_file(tmp_path)
    out = tmp_path / "report.json"
    call_command("catalog_rules_shadow", ruleset=str(ruleset), pool="in-stock", out=str(out))
    first = out.read_text(encoding="utf-8")
    with pytest.raises(CommandError, match="--force"):
        call_command("catalog_rules_shadow", ruleset=str(ruleset), pool="in-stock", out=str(out))
    assert out.read_text(encoding="utf-8") == first  # отказ без перезаписи
    call_command(
        "catalog_rules_shadow", ruleset=str(ruleset), pool="in-stock", out=str(out), force=True
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
@pytest.mark.django_db
def test_output_file_mode_0600(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    out = tmp_path / "report.json"
    call_command(
        "catalog_rules_shadow", ruleset=str(_ruleset_file(tmp_path)), pool="in-stock", out=str(out)
    )
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600


@pytest.mark.django_db
def test_printed_sha256_matches_file_bytes(tmp_path):
    """Контракт sha256= на stdout: хэш БАЙТОВ файла, не LF-payload (Windows: \r\n)."""
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт 6,4х76 оцинкованный", article="H1")
    out = tmp_path / "report.json"
    sample_out = tmp_path / "gate_sample.json"
    buf = StringIO()
    call_command(
        "catalog_rules_shadow",
        ruleset=str(_ruleset_file(tmp_path)),
        pool="in-stock",
        out=str(out),
        gate_sample_out=str(sample_out),
        stdout=buf,
    )
    printed = {}
    for line in buf.getvalue().splitlines():
        if line.startswith("artifact="):
            path_s, sha = line.removeprefix("artifact=").rsplit(" sha256=", 1)
            printed[Path(path_s)] = sha
    assert set(printed) == {out, sample_out}  # оба артефакта печатают sha256
    for path, sha in printed.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha


# --- метрики / коллизии ---


@pytest.mark.django_db
def test_collision_fully_reported(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _option(attr, "Гвозди", "krep-gvozdi")
    target = _product(original_name="Шплинт оцинкованный 6,4х76", article="F1")
    report = _run(_two_rule_ruleset(tmp_path), tmp_path / "report.json")
    assert report["counts"]["predictions"] == 0
    assert report["counts"]["collisions"] == 1
    collision = report["collisions"][0]
    assert collision["product_id"] == target.pk
    assert collision["slugs"] == ["krep-gvozdi", "krep-shplinty"]
    assert collision["rule_refs"] == ["tt-col-001", "tt-col-002"]
    per_rule = report["per_rule"]
    for ref in ("tt-col-001", "tt-col-002"):
        assert per_rule[ref]["raw_hits"] == 1
        assert per_rule[ref]["collision_hits"] == 1
        assert per_rule[ref]["prediction_hits"] == 0
        assert per_rule[ref]["coverage_share"] == 0.0


@pytest.mark.django_db
def test_per_rule_metrics(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    rules = [
        {
            "rule_ref": "tt-met-001",
            "option_slug": "krep-shplinty",
            "match": {
                "original_name_keywords_any": ["шплинт"],
                "source_group_any": ["Крепёж"],
            },
            "derived_from": [201, 202],
        },
        {
            "rule_ref": "tt-met-002",
            "option_slug": "krep-shplinty",
            "match": {
                "original_name_keywords_any": ["оцинк"],
                "source_group_any": ["Крепёж"],
            },
            "derived_from": [203, 204],
        },
    ]
    fixtures = [
        {"fixture_ref": "nf-met-001", "rule_refs": ["tt-met-001"], "name": "Пассатижи"},
        {"fixture_ref": "nf-met-002", "rule_refs": ["tt-met-002"], "name": "Молоток"},
    ]
    ruleset = _ruleset_file(tmp_path, rules=rules, fixtures=fixtures)
    _product(original_name="Шплинт оцинкованный 6,4х76", article="M1")  # матчат оба правила
    _product(original_name="Гвоздь оцинкованный 4х50", article="M2")  # только tt-met-002
    report = _run(ruleset, tmp_path / "report.json")
    assert report["counts"]["predictions"] == 2
    assert report["counts"]["collisions"] == 0  # один slug — не коллизия
    assert report["pool"]["size"] == 2
    assert report["predictions_share"] == 1.0
    per_rule = report["per_rule"]
    m1 = per_rule["tt-met-001"]
    assert m1["tier"] == "candidate"
    assert m1["raw_hits"] == 1
    assert m1["prediction_hits"] == 1
    assert m1["collision_hits"] == 0
    assert m1["same_slug_multi_hits"] == 1  # prediction по двум правилам одного slug
    assert m1["coverage_share"] == 0.5  # round(1 / 2, 4)
    m2 = per_rule["tt-met-002"]
    assert m2["raw_hits"] == 2
    assert m2["prediction_hits"] == 2
    assert m2["collision_hits"] == 0
    assert m2["same_slug_multi_hits"] == 1
    assert m2["coverage_share"] == 1.0  # round(2 / 2, 4)


# --- gate artifacts ---


@pytest.mark.django_db
def test_gate_sample_artifact(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    target = _product(original_name="Шплинт 6,4х76 оцинкованный", article="G1")
    _product(original_name="Пассатижи 180мм", article="G2")
    ruleset = _ruleset_file(tmp_path)
    corpus = _corpus_file(tmp_path, [900000901, 900000902])
    sample_out = tmp_path / "gate_sample.json"
    _run(
        ruleset,
        tmp_path / "report.json",
        sample_size=10,
        seed=42,
        gate_sample_out=str(sample_out),
        corpus=str(corpus),
    )
    artifact = json.loads(sample_out.read_text(encoding="utf-8"))
    assert artifact["version"] == 1
    assert artifact["artifact"] == "gate_sample"
    assert artifact["seed"] == 42
    assert artifact["pool"] == "in-stock"
    assert artifact["pool_filter_version"] == "1.0"
    assert artifact["matcher_version"] == "1.0"
    assert len(artifact["ruleset_hash"]) == 64
    assert len(artifact["taxonomy_hash"]) == 64
    assert [r["product_id"] for r in artifact["rows"]] == [target.pk]
    row = artifact["rows"][0]
    assert row["predicted_option_slug"] == "krep-shplinty"
    assert row["rule_refs"] == ["tt-test-001"]
    assert row["original_name"] == "Шплинт 6,4х76 оцинкованный"
    facts = {k: row[k] for k in ("name", "original_name", "brand", "source_group", "article")}
    assert row["facts_hash"] == canonical_hash(facts)
    # артефакт чист по аудитору против того же corpus
    assert validate_gate_sample(artifact, load_corpus(corpus)) == []


@pytest.mark.django_db
def test_gate_sample_corpus_overlap_rejected(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    target = _product(original_name="Шплинт 6,4х76 оцинкованный", article="H1")
    # corpus содержит товар из пула → overlap ловится по product_id
    corpus = _corpus_file(tmp_path, [target.pk])
    out = tmp_path / "report.json"
    sample_out = tmp_path / "gate_sample.json"
    with pytest.raises(CommandError, match="training corpus"):
        call_command(
            "catalog_rules_shadow",
            ruleset=str(_ruleset_file(tmp_path)),
            pool="in-stock",
            out=str(out),
            sample_size=10,
            gate_sample_out=str(sample_out),
            corpus=str(corpus),
        )
    assert not out.exists()  # отказ до записи любых артефактов
    assert not sample_out.exists()


# --- read-only / replay ---


@pytest.mark.django_db
def test_zero_writes_including_content_findings(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    target = _product(original_name="Шплинт 6,4х76 оцинкованный", article="A2")
    miss = _product(original_name="Пассатижи 180мм", article="A3")
    out = tmp_path / "report.json"
    ruleset = _ruleset_file(tmp_path)
    before = _db_counts()

    call_command(
        "catalog_rules_shadow",
        ruleset=str(ruleset),
        pool="in-stock",
        out=str(out),
        sample_size=10,
        seed=42,
    )

    assert _db_counts() == before  # ноль записей, включая ContentFinding
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["counts"]["predictions"] == 1
    assert report["counts"]["collisions"] == 0
    assert report["pool"]["name"] == "in-stock"
    ids = [p["product_id"] for p in report["predictions"]]
    assert target.pk in ids and miss.pk not in ids
    prediction = report["predictions"][0]
    assert prediction["rule_refs"] == ["tt-test-001"]
    assert prediction["evidence"]["facts"]["original_name"] == "Шплинт 6,4х76 оцинкованный"
    assert len(prediction["evidence"]["facts_hash"]) == 64
    assert prediction["evidence"]["match"]["tt-test-001"]["matched"] is True
    assert report["sample"]["seed"] == 42


@pytest.mark.django_db
def test_replay_regression_not_gate(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    corpus = _corpus_file(
        tmp_path,
        [900000801, 900000802],
        original_names=["Шплинт оцинкованный 6,4х76", "Пассатижи 180мм"],
    )
    # mismatch НЕ валит команду: replay считает recall, он не gate
    report = _run(_ruleset_file(tmp_path), tmp_path / "report.json", replay_corpus=str(corpus))
    replay = report["replay"]
    assert replay["items"] == 2
    assert replay["correct"] == 1
    assert replay["recall"] == 0.5
    assert len(replay["mismatches"]) == 1
    assert replay["mismatches"][0]["product_id"] == 900000802


# --- прочие проверки команды ---


@pytest.mark.django_db
def test_shadow_command_unknown_slug_fails(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    with pytest.raises(CommandError, match="отсутствуют в allowed"):
        call_command(
            "catalog_rules_shadow",
            ruleset=str(_ruleset_file(tmp_path, slug="net-takogo-tipa")),
            pool="in-stock",
            out=str(tmp_path / "r.json"),
        )


@pytest.mark.django_db
def test_shadow_command_sample_deterministic(tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    for i in range(5):
        _product(original_name=f"Шплинт тип {i}", article=f"S{i}")
    out1, out2 = tmp_path / "r1.json", tmp_path / "r2.json"
    ruleset = _ruleset_file(tmp_path)
    for out in (out1, out2):
        call_command(
            "catalog_rules_shadow",
            ruleset=str(ruleset),
            pool="all",
            out=str(out),
            sample_size=3,
            seed=20260721,
        )
    s1 = json.loads(out1.read_text(encoding="utf-8"))["sample"]["product_ids"]
    s2 = json.loads(out2.read_text(encoding="utf-8"))["sample"]["product_ids"]
    assert s1 == s2 and len(s1) == 3


@pytest.mark.django_db
def test_empty_ruleset_yields_zero_predictions(tmp_path):
    # пустой ruleset ("rules": []) валиден (P1.9): прогон идёт, predictions = 0
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт 6,4х76 оцинкованный", article="Z1")
    ruleset = _ruleset_file(tmp_path, rules=[], fixtures=[])
    report = _run(ruleset, tmp_path / "report.json")
    assert report["pool"]["size"] == 1
    assert report["counts"]["predictions"] == 0
    assert report["counts"]["collisions"] == 0
    assert report["counts"]["no_match"] == 1
    assert report["predictions"] == []
    assert report["per_rule"] == {}
    assert report["predictions_share"] == 0.0


@pytest.mark.django_db
def test_content_hash_deterministic_across_runs(tmp_path):
    # content_hash (canonical_hash без volatile-полей, P1.5) одинаков
    # в двух прогонах с идентичными args (P1.9)
    attr = _tool_type_attr()
    _option(attr, "Шплинты", "krep-shplinty")
    _product(original_name="Шплинт 6,4х76 оцинкованный", article="R1")
    ruleset = _ruleset_file(tmp_path)
    out = tmp_path / "report.json"
    hashes = []
    for _ in range(2):
        buf = StringIO()
        call_command(
            "catalog_rules_shadow",
            ruleset=str(ruleset),
            pool="in-stock",
            out=str(out),
            force=True,  # оба прогона с одинаковыми args → hash сравним
            stdout=buf,
        )
        m = re.search(r"content_hash=([0-9a-f]{64})", buf.getvalue())
        assert m, buf.getvalue()
        hashes.append(m.group(1))
    assert hashes[0] == hashes[1]
    # напечатанный hash совпадает с canonical_hash отчёта без volatile-полей
    report = json.loads(out.read_text(encoding="utf-8"))
    stable = {k: v for k, v in report.items() if k not in VOLATILE_REPORT_KEYS}
    assert canonical_hash(stable) == hashes[0]
