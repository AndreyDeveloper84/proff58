import threading
import time
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.catalog import processing
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogChangeStatus,
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
)
from apps.catalog.processing import canonical_hash, tool_type_snapshot


def _category():
    return Category.add_root(
        name=f"Перф-{uuid.uuid4().hex[:8]}", slug=f"perf-{uuid.uuid4().hex[:8]}"
    )


def _product(**kw):
    cat = _category()
    defaults = dict(
        category=cat,
        name="",
        slug="p",
        original_name="Перфоратор Makita HR2470",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
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


def _run():
    return CatalogProcessingRun.objects.create(
        kind="manual",
        mode="tool_type",
        status=CatalogProcessingRunStatus.RUNNING,
        idempotency_key=f"run-{CatalogProcessingRun.objects.count()}",
    )


def _item(run, product):
    snapshot = tool_type_snapshot(product)
    baseline = {"tool_type": canonical_hash(processing._operational_baseline(snapshot))}
    return CatalogProcessingItem.objects.create(
        run=run,
        product=product,
        product_ref=product.pk,
        status=CatalogProcessingItemStatus.PENDING,
        input_snapshot=snapshot,
        input_hash=canonical_hash(snapshot),
        baseline_hashes=baseline,
        needed_targets=["tool_type"],
    )


@pytest.fixture
def feature_enabled():
    old = settings.FEATURES.get("catalog_processing")
    settings.FEATURES["catalog_processing"] = True
    yield
    settings.FEATURES["catalog_processing"] = old


@pytest.fixture
def reviewer():
    User = get_user_model()
    return User.objects.create(phone="+79990000002")


@pytest.mark.django_db(transaction=True)
def test_two_parallel_decisions_at_most_one_applied(feature_enabled, reviewer):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    perforator = _option(attr, "Перфораторы", "perforatory")
    p = _product(slug="concurrent")
    run = _run()
    item = _item(run, p)

    results = []
    errors = []

    def worker(option_slug, key):
        try:
            cmd = processing.CatalogChangeCommand(
                item_id=item.pk,
                target_kind="tool_type",
                proposed_value={"option_slug": option_slug},
                source="manual",
                confidence=100,
                idempotency_key=key,
            )
            proposed = processing.create_catalog_change(cmd)
            reviewed = processing.review_catalog_change(
                proposed.change_id, CatalogChangeStatus.APPROVED, reviewer.pk
            )
            assert reviewed.status == "approved"
            results.append(processing.apply_catalog_change(proposed.change_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=worker, args=(drill.slug, "concurrent-1"))
    t2 = threading.Thread(target=worker, args=(perforator.slug, "concurrent-2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"errors: {errors}"
    applied = [r for r in results if r.status == "applied"]
    assert len(applied) == 1, f"expected one applied, got {results}"

    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    change = CatalogChange.objects.get(pk=applied[0].change_id)
    assert pav.value_option.slug == change.proposed_value["option_slug"]

    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_idempotency_under_concurrency(feature_enabled):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-idem")
    run = _run()
    item = _item(run, p)

    results = []

    def worker():
        cmd = processing.CatalogChangeCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="same-key",
        )
        results.append(processing.create_catalog_change(cmd))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    assert results[0].change_id == results[1].change_id
    assert CatalogChange.objects.filter(idempotency_key="same-key").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_apply_same_change_is_idempotent(feature_enabled, reviewer):
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-apply")
    run = _run()
    item = _item(run, p)
    proposed = processing.create_catalog_change(
        processing.CatalogChangeCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="concurrent-apply-key",
        )
    )
    processing.review_catalog_change(proposed.change_id, CatalogChangeStatus.APPROVED, reviewer.pk)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait()
            results.append(processing.apply_catalog_change(proposed.change_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert [result.status for result in results] == ["applied", "applied"]
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status == CatalogChangeStatus.APPLIED
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_concurrent_review_and_apply_is_consistent(feature_enabled, reviewer):
    """Approve и apply одновременно не приводят к расхождению audit/каталог."""
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-review-apply")
    run = _run()
    item = _item(run, p)
    proposed = processing.create_catalog_change(
        processing.CatalogChangeCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="concurrent-review-apply-key",
        )
    )

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def approve_worker():
        try:
            barrier.wait()
            results.append(
                processing.review_catalog_change(
                    proposed.change_id, CatalogChangeStatus.APPROVED, reviewer.pk
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    def apply_worker():
        try:
            barrier.wait()
            results.append(processing.apply_catalog_change(proposed.change_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=approve_worker)
    t2 = threading.Thread(target=apply_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"errors: {errors}"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status in {
        CatalogChangeStatus.APPROVED,
        CatalogChangeStatus.APPLIED,
    }
    assert change.status != CatalogChangeStatus.REJECTED
    item.refresh_from_db()
    if change.status == CatalogChangeStatus.APPLIED:
        assert item.status == CatalogProcessingItemStatus.COMPLETED
        pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
        assert pav.value_option == drill
    else:
        # apply пришёл раньше approve и корректно отклонился; каталог не изменён.
        assert item.status != CatalogProcessingItemStatus.COMPLETED
        assert not ProductAttributeValue.objects.filter(product=p, attribute=attr).exists()
        assert any(r.status == "invalid" for r in results)


@pytest.mark.django_db(transaction=True)
def test_concurrent_reject_and_apply_is_consistent(feature_enabled, reviewer):
    """Reject и apply одновременно не применяют изменение к каталогу."""
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-reject-apply")
    run = _run()
    item = _item(run, p)
    proposed = processing.create_catalog_change(
        processing.CatalogChangeCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="concurrent-reject-apply-key",
        )
    )

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def reject_worker():
        try:
            barrier.wait()
            results.append(
                processing.review_catalog_change(
                    proposed.change_id, CatalogChangeStatus.REJECTED, reviewer.pk
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    def apply_worker():
        try:
            barrier.wait()
            results.append(processing.apply_catalog_change(proposed.change_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=reject_worker)
    t2 = threading.Thread(target=apply_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"errors: {errors}"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status == CatalogChangeStatus.REJECTED
    item.refresh_from_db()
    assert item.status != CatalogProcessingItemStatus.COMPLETED
    assert not ProductAttributeValue.objects.filter(product=p, attribute=attr).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_approve_and_reject_is_consistent(feature_enabled, reviewer):
    """Одновременный approve и reject не переписывают финальное решение."""
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-approve-reject")
    run = _run()
    item = _item(run, p)
    proposed = processing.create_catalog_change(
        processing.CatalogChangeCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="concurrent-approve-reject-key",
        )
    )

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker(decision):
        try:
            barrier.wait()
            results.append(
                processing.review_catalog_change(proposed.change_id, decision, reviewer.pk)
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=worker, args=(CatalogChangeStatus.APPROVED,))
    t2 = threading.Thread(target=worker, args=(CatalogChangeStatus.REJECTED,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"errors: {errors}"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status in {
        CatalogChangeStatus.APPROVED,
        CatalogChangeStatus.REJECTED,
    }
    statuses = {r.status for r in results}
    # Один поток выиграл, другой увидел финальный статус.
    assert CatalogChangeStatus.APPLIED not in statuses
    item.refresh_from_db()
    if change.status == CatalogChangeStatus.REJECTED:
        # Победивший reject завершает item: открытых changes не осталось.
        assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
        assert item.error_code == "rejected"
    else:
        # Победивший approve не трогает item (fixture создаёт его pending).
        assert item.status == CatalogProcessingItemStatus.PENDING
        assert item.error_code == ""


@pytest.mark.django_db(transaction=True)
def test_exception_after_pav_write_marks_failed(feature_enabled, reviewer, monkeypatch):
    """Если apply падает после записи PAV, audit остаётся failed, каталог откатывается."""
    from apps.catalog import processing as processing_module

    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-exception")
    run = _run()
    item = _item(run, p)
    proposed = processing.create_catalog_change(
        processing.CatalogChangeCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="exception-after-pav-key",
        )
    )
    processing.review_catalog_change(proposed.change_id, CatalogChangeStatus.APPROVED, reviewer.pk)

    def exploding_rebuild(product):
        # Проверяем, что PAV уже записан внутри транзакции.
        assert ProductAttributeValue.objects.filter(product=product, attribute=attr).exists()
        raise RuntimeError("simulated cache failure")

    monkeypatch.setattr(processing_module, "rebuild_attrs_cache", exploding_rebuild)

    result = processing.apply_catalog_change(proposed.change_id)

    assert result.status == "failed"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status == CatalogChangeStatus.FAILED
    assert change.reason_code == "apply_exception"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.FAILED
    # Каталог откатился вместе с транзакцией.
    assert not ProductAttributeValue.objects.filter(product=p, attribute=attr).exists()

    # Восстанавливаем для чистоты (monkeypatch сделает это автоматически, но явно надёжнее).
    monkeypatch.undo()


@pytest.mark.django_db(transaction=True)
def test_two_parallel_finalize_calls_single_transition(feature_enabled):
    p = _product(slug="finalize-concurrent")
    run = _run()
    item = _item(run, p)
    item.status = CatalogProcessingItemStatus.COMPLETED
    item.save(update_fields=["status"])

    results = []
    errors = []

    def worker():
        try:
            results.append(processing.finalize_catalog_processing_run(run.id))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 2
    assert all(r.status == "completed" for r in results)
    # Ровно один поток выполнил переход, второй получил идемпотентный ответ.
    assert sum(1 for r in results if not r.already_finalized) == 1
    assert sum(1 for r in results if r.already_finalized) == 1
    run.refresh_from_db()
    assert run.status == CatalogProcessingRunStatus.COMPLETED
    assert run.finished_at is not None
