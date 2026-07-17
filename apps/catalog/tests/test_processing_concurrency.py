import threading
import time

import pytest

from apps.catalog import processing
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
)
from apps.catalog.processing import apply_catalog_decision, canonical_hash, tool_type_snapshot


def _category():
    return Category.add_root(name="Перф", slug="perf")


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


@pytest.mark.django_db(transaction=True)
def test_two_parallel_decisions_at_most_one_applied():
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
            cmd = processing.CatalogDecisionCommand(
                item_id=item.pk,
                target_kind="tool_type",
                proposed_value={"option_slug": option_slug},
                source="manual",
                confidence=100,
                idempotency_key=key,
            )
            results.append(apply_catalog_decision(cmd))
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
    applied_slug = applied[0].change_id
    change = CatalogChange.objects.get(pk=applied_slug)
    assert pav.value_option.slug == change.proposed_value["option_slug"]


@pytest.mark.django_db(transaction=True)
def test_idempotency_under_concurrency():
    attr = _tool_type_attr()
    drill = _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")
    p = _product(slug="concurrent-idem")
    run = _run()
    item = _item(run, p)

    results = []

    def worker():
        cmd = processing.CatalogDecisionCommand(
            item_id=item.pk,
            target_kind="tool_type",
            proposed_value={"option_slug": drill.slug},
            source="manual",
            confidence=100,
            idempotency_key="same-key",
        )
        results.append(apply_catalog_decision(cmd))

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
