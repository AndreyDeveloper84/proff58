import json
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    Category,
    Product,
    ProductStatus,
)
from apps.catalog.processing import canonical_hash


@pytest.fixture
def feature_enabled():
    old = settings.FEATURES.get("catalog_processing")
    settings.FEATURES["catalog_processing"] = True
    yield
    settings.FEATURES["catalog_processing"] = old


def _category():
    return Category.add_root(
        name=f"Перф-{uuid.uuid4().hex[:8]}", slug=f"perf-{uuid.uuid4().hex[:8]}"
    )


def _product(**kw):
    cat = _category()
    defaults = dict(
        category=cat,
        name="",
        slug=f"p-{uuid.uuid4().hex[:8]}",
        original_name="Перфоратор Makita HR2470",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        available_quantity="10",
    )
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _tool_type_attr():
    attr, _ = Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )
    return attr


def _option(attr, value, slug):
    return AttributeOption.objects.get_or_create(
        attribute=attr, value=value, defaults={"slug": slug}
    )[0]


def _result_item(item, option_slug, source="web", confidence=95):
    return {
        "product_ref": item.product_ref,
        "input_hash": item.input_hash,
        "identity": {"status": "matched", "brand": "Test", "model": "Model"},
        "status": "researched",
        "changes": [
            {
                "target_kind": "tool_type",
                "proposed_value": {"option_slug": option_slug},
                "confidence": confidence,
                "reason_code": "exact_model_match",
                "source": source,
                "evidence": [
                    {
                        "source_type": "manufacturer",
                        "url": "https://example.com/product",
                        "title": "Product page",
                        "observed_value": "test",
                        "retrieved_at": timezone.now().isoformat(),
                    }
                ],
            }
        ],
    }


def _export_run(run_id: str, tmp_path: Path) -> dict:
    export_path = tmp_path / f"{run_id}.export.json"
    call_command("catalog_queue_export", "--run", run_id, "--output", str(export_path))
    return json.loads(export_path.read_text(encoding="utf-8"))


def _write_result(path: Path, run_id: str, items: list, export_data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": "1.0",
        "run_id": str(run_id),
        "taxonomy_hash": export_data["taxonomy_hash"],
        "export_checksum": export_data["checksum"],
        "items": items,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _import_result(path: Path, *, commit: bool = False, run_id: str | None = None):
    args = ["catalog_queue_import", "--file", str(path), "--allow-external-path"]
    if commit:
        args.append("--commit")
    if run_id:
        args.extend(["--run", run_id])
    return call_command(*args)


@pytest.mark.django_db
def test_create_run_with_untyped_in_stock(feature_enabled):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p1 = _product(available_quantity="10")
    _product(available_quantity="0")  # out of stock

    out = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-create-1",
    )

    run = CatalogProcessingRun.objects.get(pk=out)
    assert run.kind == "research"
    assert run.mode == "tool_type"
    assert run.status == "running"
    assert run.items.count() == 1
    item = run.items.first()
    assert item.product_ref == p1.pk
    assert item.input_hash == canonical_hash(
        {
            "product_id": p1.pk,
            "code_1c": "",
            "article": "",
            "barcode": "",
            "brand": "",
            "name": "",
            "original_name": p1.original_name,
            "category_id": p1.category_id,
            "category_path": p1.category.name,
            "source_group": "",
        }
    )


@pytest.mark.django_db
def test_create_is_idempotent(feature_enabled):
    _tool_type_attr()
    _product(available_quantity="10")

    out1 = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-create-idem",
    )
    out2 = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-create-idem",
    )

    assert out1 == out2
    assert CatalogProcessingRun.objects.filter(idempotency_key="test-create-idem").count() == 1


@pytest.mark.django_db
def test_export_is_deterministic(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _ = _product(available_quantity="10")
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-export-det",
    )

    out1 = tmp_path / "a.json"
    out2 = tmp_path / "b.json"
    call_command("catalog_queue_export", "--run", run_id, "--output", str(out1))
    call_command("catalog_queue_export", "--run", run_id, "--output", str(out2))

    data1 = json.loads(out1.read_text(encoding="utf-8"))
    data2 = json.loads(out2.read_text(encoding="utf-8"))
    assert data1["checksum"] == data2["checksum"]
    assert data1["items"] == data2["items"]
    assert data1["taxonomy_hash"] == data2["taxonomy_hash"]
    assert any(opt["slug"] == drill.slug for opt in data1["allowed_options"])


@pytest.mark.django_db
def test_import_dry_run_does_not_create_changes(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _ = _product(available_quantity="10")
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-dry",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.first()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "result.json"
    _write_result(result_path, run_id, [_result_item(item, drill.slug)], export_data)

    result = json.loads(_import_result(result_path))

    assert CatalogChange.objects.filter(item__run=run).count() == 0
    assert result["would_create"] == 1
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.PENDING


@pytest.mark.django_db
def test_import_commit_creates_proposed_changes(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _ = _product(available_quantity="10")
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-commit",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.first()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "result.json"
    _write_result(result_path, run_id, [_result_item(item, drill.slug)], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    changes = list(CatalogChange.objects.filter(item__run=run))
    assert len(changes) == 1
    assert result["created"] == 1
    assert changes[0].status == "proposed"
    assert changes[0].proposed_value == {"option_slug": drill.slug}
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.PROCESSING


@pytest.mark.django_db
def test_import_rejects_unknown_option(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _ = _product(available_quantity="10")
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-unknown",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.first()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "result.json"
    _write_result(result_path, run_id, [_result_item(item, "no-such-option")], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    assert CatalogChange.objects.filter(item__run=run).count() == 0
    assert result["errors"] == 1
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "import_error"
    report = json.loads(call_command("catalog_queue_status", "--run", run_id))
    assert report["errors"][0]["product_ref"] == item.product_ref


@pytest.mark.django_db
def test_import_rejects_changed_input_hash(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _ = _product(available_quantity="10")
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-hash",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.first()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "result.json"
    bad_item = _result_item(item, drill.slug)
    bad_item["input_hash"] = "0" * 64
    _write_result(result_path, run_id, [bad_item], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    assert CatalogChange.objects.filter(item__run=run).count() == 0
    assert result["errors"] == 1


@pytest.mark.django_db
def test_status_report(feature_enabled):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product(available_quantity="10")
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-status",
    )

    out = call_command("catalog_queue_status", "--run", run_id)
    report = json.loads(out)
    assert report["run_id"] == run_id
    assert report["items"]["total"] == 1
    assert report["changes"]["total"] == 0


@pytest.mark.django_db
def test_import_same_file_twice_is_idempotent(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-repeat",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "repeat.result.json"
    _write_result(result_path, run_id, [_result_item(item, drill.slug)], export_data)

    first = json.loads(_import_result(result_path, commit=True))
    second = json.loads(_import_result(result_path, commit=True))

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["existing"] == 1
    assert CatalogChange.objects.filter(item__run=run).count() == 1


@pytest.mark.django_db
def test_import_rejects_untrusted_manual_source(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-manual-source",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    export_data = _export_run(run_id, tmp_path)
    item_data = _result_item(run.items.get(), drill.slug, source="manual")
    result_path = tmp_path / "manual.result.json"
    _write_result(result_path, run_id, [item_data], export_data)

    with pytest.raises(CommandError, match="JSON Schema"):
        _import_result(result_path, commit=True)

    assert not CatalogChange.objects.filter(item__run=run).exists()


@pytest.mark.django_db
def test_import_requires_matched_identity(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-identity",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    export_data = _export_run(run_id, tmp_path)
    item_data = _result_item(run.items.get(), drill.slug)
    item_data["identity"]["status"] = "partial"
    result_path = tmp_path / "identity.result.json"
    _write_result(result_path, run_id, [item_data], export_data)

    with pytest.raises(CommandError, match="identity.status=matched"):
        _import_result(result_path, commit=True)

    assert not CatalogChange.objects.filter(item__run=run).exists()


@pytest.mark.django_db
def test_import_rejects_taxonomy_or_export_mismatch(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-taxonomy",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "taxonomy.result.json"
    result = _write_result(
        result_path, run_id, [_result_item(run.items.get(), drill.slug)], export_data
    )
    result["taxonomy_hash"] = "0" * 64
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(CommandError, match="taxonomy_hash"):
        _import_result(result_path, commit=True)

    assert not CatalogChange.objects.filter(item__run=run).exists()


@pytest.mark.django_db
def test_import_rejects_stale_current_input(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    product = _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-stale-input",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    export_data = _export_run(run_id, tmp_path)
    item = run.items.get()
    result_path = tmp_path / "stale.result.json"
    _write_result(result_path, run_id, [_result_item(item, drill.slug)], export_data)
    product.original_name = "Изменённое название после export"
    product.save(update_fields=["original_name"])

    stats = json.loads(_import_result(result_path, commit=True))

    assert stats["errors"] == 1
    assert not CatalogChange.objects.filter(item__run=run).exists()


@pytest.mark.django_db
def test_import_rolls_back_whole_item_on_invalid_second_change(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-item-atomic",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    export_data = _export_run(run_id, tmp_path)
    item_data = _result_item(run.items.get(), drill.slug)
    invalid_change = dict(item_data["changes"][0])
    invalid_change["proposed_value"] = {"option_slug": "no-such-option"}
    item_data["changes"].append(invalid_change)
    result_path = tmp_path / "atomic.result.json"
    _write_result(result_path, run_id, [item_data], export_data)

    stats = json.loads(_import_result(result_path, commit=True))

    assert stats["errors"] == 1
    assert not CatalogChange.objects.filter(item__run=run).exists()


@pytest.mark.django_db
def test_import_rejects_run_override_mismatch(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-import-run-mismatch",
    )
    run = CatalogProcessingRun.objects.get(pk=run_id)
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "run-mismatch.result.json"
    _write_result(result_path, run_id, [_result_item(run.items.get(), drill.slug)], export_data)

    with pytest.raises(CommandError, match="не совпадает"):
        _import_result(result_path, run_id=str(uuid.uuid4()))


@pytest.mark.django_db
def test_import_blocks_external_path_by_default(feature_enabled, tmp_path):
    result_path = tmp_path / "external.result.json"
    result_path.write_text("{}", encoding="utf-8")

    with pytest.raises(CommandError, match="должен находиться"):
        call_command("catalog_queue_import", "--file", str(result_path))


@pytest.mark.django_db
def test_export_checksum_independent_of_pretty_format(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-export-pretty",
    )
    compact_path = tmp_path / "compact.json"
    pretty_path = tmp_path / "pretty.json"

    call_command("catalog_queue_export", "--run", run_id, "--output", str(compact_path))
    call_command("catalog_queue_export", "--run", run_id, "--output", str(pretty_path), "--pretty")

    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    pretty = json.loads(pretty_path.read_text(encoding="utf-8"))
    assert compact["checksum"] == pretty["checksum"]


@pytest.mark.django_db
def test_reexport_rejects_changed_taxonomy(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    _product()
    run_id = call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        "test-export-taxonomy-change",
    )
    _export_run(run_id, tmp_path)
    _option(attr, "Перфораторы", "perforatory")

    with pytest.raises(CommandError, match="Taxonomy изменилась"):
        call_command(
            "catalog_queue_export",
            "--run",
            run_id,
            "--output",
            str(tmp_path / "changed.json"),
        )


def _abstain_item(item, status="review", reason="нет точного slug в allowed_options"):
    return {
        "product_ref": item.product_ref,
        "input_hash": item.input_hash,
        "identity": {"status": "matched", "brand": "Test", "model": "Model"},
        "status": status,
        "reason_code": "no_exact_slug",
        "reason_detail": reason,
        "changes": [],
    }


def _make_run(idem_key):
    _product()
    return call_command(
        "catalog_queue_create",
        "--only-untyped",
        "--in-stock",
        "--limit",
        "10",
        "--idempotency-key",
        idem_key,
    )


@pytest.mark.django_db
def test_import_review_without_changes_marks_needs_review(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    run_id = _make_run("test-import-review-needs-review")
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "review.result.json"
    _write_result(result_path, run_id, [_abstain_item(item)], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    assert result["skipped"] == 1
    assert result["errors"] == 0
    assert not CatalogChange.objects.filter(item__run=run).exists()
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "review"
    assert item.error_detail == "нет точного slug в allowed_options"


@pytest.mark.django_db
def test_import_review_dry_run_writes_nothing(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    run_id = _make_run("test-import-review-dry-run")
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "review.result.json"
    _write_result(result_path, run_id, [_abstain_item(item)], export_data)

    result = json.loads(_import_result(result_path))

    assert result["skipped"] == 1
    assert result["errors"] == 0
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.PENDING
    assert item.error_code == ""
    assert not CatalogChange.objects.filter(item__run=run).exists()


@pytest.mark.django_db
def test_import_review_commit_replay_is_idempotent(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    run_id = _make_run("test-import-review-replay")
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    result_path = tmp_path / "review.result.json"
    _write_result(result_path, run_id, [_abstain_item(item)], export_data)

    first = json.loads(_import_result(result_path, commit=True))
    second = json.loads(_import_result(result_path, commit=True))

    assert first["skipped"] == second["skipped"] == 1
    assert first["errors"] == second["errors"] == 0
    assert not CatalogChange.objects.filter(item__run=run).exists()
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "review"


@pytest.mark.django_db
def test_import_researched_without_changes_is_contract_error(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    run_id = _make_run("test-import-researched-empty")
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    item_data = _abstain_item(item, status="researched")
    result_path = tmp_path / "researched.result.json"
    _write_result(result_path, run_id, [item_data], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    assert result["errors"] == 1
    assert not CatalogChange.objects.filter(item__run=run).exists()
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "import_error"


@pytest.mark.django_db
def test_import_unknown_with_changes_rejected(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    run_id = _make_run("test-import-unknown-with-changes")
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    item_data = _result_item(item, drill.slug)
    item_data["status"] = "unknown"
    result_path = tmp_path / "unknown.result.json"
    _write_result(result_path, run_id, [item_data], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    assert result["errors"] == 1
    assert not CatalogChange.objects.filter(item__run=run).exists()
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "import_error"


@pytest.mark.django_db
def test_import_identity_failed_with_changes_rejected(feature_enabled, tmp_path):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    run_id = _make_run("test-import-identity-failed-with-changes")
    run = CatalogProcessingRun.objects.get(pk=run_id)
    item = run.items.get()
    export_data = _export_run(run_id, tmp_path)
    item_data = _result_item(item, drill.slug)
    item_data["status"] = "identity_failed"
    result_path = tmp_path / "identity_failed.result.json"
    _write_result(result_path, run_id, [item_data], export_data)

    result = json.loads(_import_result(result_path, commit=True))

    assert result["errors"] == 1
    assert not CatalogChange.objects.filter(item__run=run).exists()
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "import_error"
