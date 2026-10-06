"""DRF-2738: команды обогащения пишут частями, а не одной транзакцией на прогон.

Проверяем ровно то, ради чего менялся контур: блокировки живут не дольше записи
одного чанка; сбой посередине оставляет записанные чанки и честный ``ImportRun``;
PAV и ``attrs_cache`` товара коммитятся вместе; отчёт dry-run не зависит от размера
чанка. Словарь правил — настоящий (``data/attribute_rules.json``,
``data/tool_type_rules.json``), как в соседних тестах команд.
"""

from __future__ import annotations

import json
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.catalog import attrs_cache, enrich_chunks
from apps.catalog.management.commands import enrich_attributes as attrs_cmd
from apps.catalog.management.commands import enrich_tool_type as tt_cmd
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    EnrichmentLog,
    ImportRun,
    Product,
    ProductAttributeValue,
    Source,
)
from apps.catalog.read_models import build_attrs_cache

pytestmark = pytest.mark.django_db

DRILLS = [
    "Дрель-шуруповёрт аккумуляторный 18В бесщёточный 55 Нм",
    "Дрель-шуруповёрт аккумуляторный 12В 30 Нм",
    "Дрель-шуруповёрт сетевой 710 Вт",
    "Дрель ударная 850 Вт",
    "Дрель-шуруповёрт аккумуляторный 20В 60 Нм",
]


@pytest.fixture
def drills(db):
    """Пять дрелей с tool_type (как после enrich_tool_type) и загруженный словарь осей."""
    top = Category.add_root(name="Электроинструмент", slug="elektroinstrument", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    option = AttributeOption.objects.create(
        attribute=tool_type, value="Дрели и шуруповёрты", slug="dreli-shurupoverty"
    )
    products = []
    for i, name in enumerate(DRILLS):
        product = Product.objects.create(category=top, name=name, slug=f"d{i}", code_1c=f"d{i}")
        ProductAttributeValue.objects.create(
            product=product, attribute=tool_type, value_option=option, source=Source.MANUAL
        )
        products.append(product)
    call_command("load_attributes")
    return products


@pytest.fixture
def chunk_of_two(monkeypatch):
    monkeypatch.setattr(enrich_chunks, "CHUNK_PRODUCTS", 2)


def _attrs_report(*args) -> dict:
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--dry-run", *args, stdout=out, stderr=err)
    return json.loads(out.getvalue())


def _managed_cache(product: Product) -> dict:
    """attrs_cache по управляемым осям, пересобранный из PAV, — для сверки с записанным."""
    full = build_attrs_cache(product)
    return {k: v for k, v in full.items() if k != "tool_type"}


def _engine_pav_count() -> int:
    return ProductAttributeValue.objects.exclude(attribute__slug="tool_type").count()


# ═══════════ отчёт не зависит от размера чанка ═══════════


def test_attrs_dry_run_is_identical_for_any_chunk_size(drills, monkeypatch):
    big = _attrs_report()
    monkeypatch.setattr(enrich_chunks, "CHUNK_PRODUCTS", 2)
    small = _attrs_report()
    for report in (big, small):
        report.pop("generated_at")
    assert small == big
    assert len(big["rows"]) > 0 and ImportRun.objects.count() == 0


def test_tool_type_dry_run_is_identical_for_any_chunk_size(monkeypatch):
    root = Category.add_root(name="Электроинструмент", slug="elektro", on_site=True)
    for i in range(5):
        Product.objects.create(
            code_1c=f"p{i}", name=f"Перфоратор Bosch {i}", category=root, slug=f"p{i}"
        )
    Product.objects.create(code_1c="u", name="Удлинитель силовой", category=root, slug="u")
    call_command("load_tool_types")

    big = call_command("enrich_tool_type", "--dry-run", stdout=StringIO())
    monkeypatch.setattr(enrich_chunks, "CHUNK_PRODUCTS", 2)
    small = call_command("enrich_tool_type", "--dry-run", stdout=StringIO())

    assert small == big


# ═══════════ сбой посередине ═══════════


def test_failure_in_second_chunk_keeps_first_and_marks_run_failed(drills, chunk_of_two):
    """Чанк 1 записан, чанк 2 откатился целиком, ImportRun честный; повтор доводит."""
    real = attrs_cache.flush_attrs_cache_merged
    calls = []

    def flaky(products, managed_for, **kwargs):
        calls.append(len(products))
        if len(calls) == 2:
            raise RuntimeError("deadlock detected")
        return real(products, managed_for, **kwargs)

    with mock.patch.object(attrs_cmd, "flush_attrs_cache_merged", side_effect=flaky):
        with pytest.raises(RuntimeError):
            call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    run = ImportRun.objects.get(source="enrich_attributes")
    assert run.status == "failed"
    assert run.stats["committed"] == 2
    assert run.stats["processed"] == 2  # счётчики — на момент последнего коммита
    assert "deadlock" in run.stats["error"]
    first_two = {p.pk for p in sorted(drills, key=lambda p: (p.name, p.pk))[:2]}
    written = set(
        ProductAttributeValue.objects.exclude(attribute__slug="tool_type")
        .values_list("product_id", flat=True)
        .distinct()
    )
    assert written == first_two
    for product in Product.objects.filter(pk__in=first_two):
        assert product.attrs_cache and _managed_cache(product) == {
            k: v for k, v in product.attrs_cache.items() if k != "tool_type"
        }
    for product in Product.objects.exclude(pk__in=first_two):
        assert not product.attrs_cache

    # Довод: повторный запуск записывает остальное, следующий dry-run — пустой.
    call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())
    assert ImportRun.objects.filter(source="enrich_attributes", status="done").exists()
    report = _attrs_report()
    assert {r["action"] for r in report["rows"]} <= {"keep"}


def test_pav_and_cache_of_a_chunk_commit_together(drills, chunk_of_two):
    """Встречный сбой — на вставке PAV: кэш тоже не записан (и наоборот)."""
    real = ProductAttributeValue.objects.bulk_create
    calls = []

    def flaky(objs, **kwargs):
        calls.append(len(objs))
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(objs, **kwargs)

    with mock.patch.object(ProductAttributeValue.objects, "bulk_create", side_effect=flaky):
        with pytest.raises(RuntimeError):
            call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    for product in Product.objects.all():
        stored = {k: v for k, v in (product.attrs_cache or {}).items() if k != "tool_type"}
        assert stored == _managed_cache(product), f"кэш и PAV разошлись у {product.name}"


def test_keyboard_interrupt_between_chunks_does_not_leave_run_running(drills, chunk_of_two):
    real = attrs_cmd.Command._load_chunk
    calls = []

    def interrupting(scoped, chunk_ids):
        calls.append(chunk_ids)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real(scoped, chunk_ids)

    with mock.patch.object(attrs_cmd.Command, "_load_chunk", staticmethod(interrupting)):
        with pytest.raises(KeyboardInterrupt):
            call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    run = ImportRun.objects.get(source="enrich_attributes")
    assert run.status == "failed" and run.stats["interrupted"] is True
    assert run.stats["committed"] == 2 and run.finished_at is not None


def test_runtime_guard_in_second_chunk_keeps_first_chunk(drills, chunk_of_two, monkeypatch):
    """Опция исчезла между preflight и записью: первый чанк остаётся, сообщение
    говорит, сколько записано (двухчанковый вариант теста из test_foundation_axes_01)."""
    from apps.catalog import attribute_preflight as preflight

    real_check = preflight.check_select_options

    def check_then_drop(required, option_index):
        missing = real_check(required, option_index)
        # «Бесщёточный» извлекается только у дрели из второго чанка (порядок — по имени).
        option_index["motor_type"].clear()
        return missing

    monkeypatch.setattr(preflight, "check_select_options", check_then_drop)
    with pytest.raises(CommandError, match=r"прогон прерван.*Записано товаров до сбоя: 2") as exc:
        call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())
    assert exc.value.returncode == 2
    run = ImportRun.objects.get(source="enrich_attributes")
    assert run.status == "failed" and run.stats["committed"] == 2
    assert _engine_pav_count() > 0  # первый чанк на месте


# ═══════════ блокировки не копятся ═══════════


def test_locks_live_only_inside_chunk_write(drills, chunk_of_two):
    base = len(connection.atomic_blocks)
    depths = {"load": set(), "write": set()}
    real_load = attrs_cmd.Command._load_chunk
    real_flush = attrs_cache.flush_attrs_cache_merged

    def spy_load(scoped, chunk_ids):
        depths["load"].add(len(connection.atomic_blocks) - base)
        return real_load(scoped, chunk_ids)

    def spy_flush(products, managed_for, **kwargs):
        depths["write"].add(len(connection.atomic_blocks) - base)
        return real_flush(products, managed_for, **kwargs)

    with (
        mock.patch.object(attrs_cmd.Command, "_load_chunk", staticmethod(spy_load)),
        mock.patch.object(attrs_cmd, "flush_attrs_cache_merged", side_effect=spy_flush),
    ):
        call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    assert depths["load"] == {0}  # чтение и решения — вне транзакции
    assert depths["write"] == {1}  # запись — ровно одна транзакция на чанк
    assert ImportRun.objects.get().stats["committed"] == len(drills)


def test_write_locks_products_before_pav(drills):
    """Порядок замков как в остальном проекте: сначала строки товаров по id, потом PAV."""
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    sqls = [q["sql"] for q in queries]
    lock = next(
        i for i, s in enumerate(sqls) if "FOR NO KEY UPDATE" in s and '"catalog_product"' in s
    )
    first_pav_write = next(
        i
        for i, s in enumerate(sqls)
        if s.startswith(("INSERT", "UPDATE", "DELETE")) and "productattributevalue" in s
    )
    assert lock < first_pav_write


@pytest.mark.django_db(transaction=True)
def test_second_writing_run_is_refused_while_first_holds_the_lock(drills):
    """Замок сессионный — вторая копия должна прийти из другого соединения."""
    import threading

    held = threading.Event()
    release = threading.Event()

    def other_session():
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s))", [enrich_chunks.WRITE_LOCK_NAME]
                )
                assert cur.fetchone()[0]
                held.set()
                release.wait(10)
                cur.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))", [enrich_chunks.WRITE_LOCK_NAME]
                )
        finally:
            connection.close()

    thread = threading.Thread(target=other_session)
    thread.start()
    assert held.wait(5)
    try:
        with pytest.raises(CommandError, match="уже идёт другой пишущий прогон"):
            call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())
        _attrs_report()  # dry-run замок не нужен
    finally:
        release.set()
        thread.join()


# ═══════════ enrich_tool_type ═══════════


def test_tool_type_failure_in_second_chunk_keeps_first_chunk_and_its_log(chunk_of_two):
    root = Category.add_root(name="Электроинструмент", slug="elektro", on_site=True)
    for i in range(5):
        Product.objects.create(
            code_1c=f"p{i}", name=f"Перфоратор Bosch {i}", category=root, slug=f"p{i}"
        )
    call_command("load_tool_types")
    real = attrs_cache.flush_attrs_cache_merged
    calls = []

    def flaky(products, managed_for, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(products, managed_for, **kwargs)

    with mock.patch.object(tt_cmd, "flush_attrs_cache_merged", side_effect=flaky):
        with pytest.raises(RuntimeError):
            call_command("enrich_tool_type", stdout=StringIO())

    run = ImportRun.objects.get(source="enrich_tool_type")
    assert run.status == "failed" and run.stats["committed"] == 2
    assert EnrichmentLog.objects.filter(run=run).count() == 2  # журнал второго чанка откатился
    assert ProductAttributeValue.objects.filter(attribute__slug="tool_type").count() == 2

    call_command("enrich_tool_type", stdout=StringIO())
    done = ImportRun.objects.get(source="enrich_tool_type", status="done")
    assert done.stats["committed"] == 5
    assert ProductAttributeValue.objects.filter(attribute__slug="tool_type").count() == 5


def test_tool_type_gaps_ignores_failed_runs(chunk_of_two):
    root = Category.add_root(name="Электроинструмент", slug="elektro", on_site=True)
    Product.objects.create(code_1c="u1", name="Удлинитель силовой 50м", category=root, slug="u1")
    Product.objects.create(code_1c="u2", name="Удлинитель садовый 20м", category=root, slug="u2")
    Product.objects.create(code_1c="u3", name="Удлинитель бытовой 5м", category=root, slug="u3")
    call_command("load_tool_types")
    call_command("enrich_tool_type", stdout=StringIO())
    ImportRun.objects.create(source="enrich_tool_type", status="failed", stats={})

    out = StringIO()
    call_command("tool_type_gaps", stdout=out)

    assert "удлинитель" in out.getvalue().lower()


def _perforators(n: int):
    root = Category.add_root(name="Электроинструмент", slug="elektro", on_site=True)
    products = [
        Product.objects.create(
            code_1c=f"p{i}", name=f"Перфоратор Bosch {i}", category=root, slug=f"p{i}"
        )
        for i in range(n)
    ]
    call_command("load_tool_types")
    return products


def test_created_options_survive_in_failed_run(chunk_of_two):
    """Опция из манифеста создана в фазе решений и при откате чанка остаётся —
    rollback-map обязан увидеть её и у прерванного прогона."""
    _perforators(3)
    AttributeOption.objects.filter(attribute__slug="tool_type", slug="perforatory").delete()

    with mock.patch.object(tt_cmd, "flush_attrs_cache_merged", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            call_command("enrich_tool_type", stdout=StringIO())

    run = ImportRun.objects.get(source="enrich_tool_type")
    assert run.status == "failed" and run.stats["committed"] == 0
    assert run.stats["created_options"] == ["perforatory"]
    assert AttributeOption.objects.filter(attribute__slug="tool_type", slug="perforatory").exists()


def test_facets_cache_is_invalidated_even_when_run_fails(drills, chunk_of_two):
    real = attrs_cache.flush_attrs_cache_merged
    calls = []

    def flaky(products, managed_for, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(products, managed_for, **kwargs)

    with (
        mock.patch.object(attrs_cmd, "flush_attrs_cache_merged", side_effect=flaky),
        mock.patch.object(attrs_cmd, "invalidate_facets_cache") as invalidate,
    ):
        with pytest.raises(RuntimeError):
            call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    invalidate.assert_called_once()  # первый чанк записан — витрине нужен свежий кэш


def test_refused_second_run_leaves_no_failed_import_run(drills):
    import threading

    held, release = threading.Event(), threading.Event()

    def other_session():
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s))", [enrich_chunks.WRITE_LOCK_NAME]
                )
                held.set()
                release.wait(10)
                cur.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))", [enrich_chunks.WRITE_LOCK_NAME]
                )
        finally:
            connection.close()

    thread = threading.Thread(target=other_session)
    thread.start()
    assert held.wait(5)
    try:
        with pytest.raises(CommandError):
            call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())
        with pytest.raises(CommandError):
            call_command("enrich_tool_type", stdout=StringIO())
    finally:
        release.set()
        thread.join()
    assert not ImportRun.objects.exists()


def test_tool_type_dry_run_opens_no_transaction_and_writes_nothing(chunk_of_two):
    _perforators(3)
    base = len(connection.atomic_blocks)
    depths = set()
    real = tt_cmd.Command._load_chunk

    def spy(qs, chunk_ids):
        depths.add(len(connection.atomic_blocks) - base)
        return real(qs, chunk_ids)

    with mock.patch.object(tt_cmd.Command, "_load_chunk", staticmethod(spy)):
        call_command("enrich_tool_type", "--dry-run", stdout=StringIO())

    assert depths == {0}
    assert not ImportRun.objects.exists() and not EnrichmentLog.objects.exists()


def test_product_dropped_between_listing_and_chunk_is_skipped(chunk_of_two):
    """Категорию товара сняли, пока шёл прогон: товар выпадает из чанка, а не роняет его."""
    _perforators(4)
    real = tt_cmd.Command._load_chunk
    calls = []

    def dropping(qs, chunk_ids):
        calls.append(chunk_ids)
        if len(calls) == 2:
            Product.objects.filter(pk=chunk_ids[0]).update(category=None)
        return real(qs, chunk_ids)

    with mock.patch.object(tt_cmd.Command, "_load_chunk", staticmethod(dropping)):
        call_command("enrich_tool_type", stdout=StringIO())

    run = ImportRun.objects.get(source="enrich_tool_type", status="done")
    assert run.stats["processed"] == 3 and run.stats["committed"] == 4
    assert ProductAttributeValue.objects.filter(attribute__slug="tool_type").count() == 3


def test_tool_type_limit_and_product_ids_with_chunks(monkeypatch):
    products = _perforators(5)
    big = call_command("enrich_tool_type", "--dry-run", "--limit", "3", stdout=StringIO())
    monkeypatch.setattr(enrich_chunks, "CHUNK_PRODUCTS", 2)
    small = call_command("enrich_tool_type", "--dry-run", "--limit", "3", stdout=StringIO())
    assert small == big

    ids = ",".join(str(p.pk) for p in products[:3])
    call_command("enrich_tool_type", "--product-ids", ids, stdout=StringIO())
    assert ProductAttributeValue.objects.filter(attribute__slug="tool_type").count() == 3


def test_quarantined_product_on_chunk_boundary(drills, chunk_of_two, tmp_path):
    """Карантинный товар — второй в первом чанке: `continue` не перескакивает запись
    соседей, товар учитывается в committed, но PAV ему не пишутся."""
    import json

    ordered = sorted(drills, key=lambda p: (p.name, p.pk))
    victim = ordered[1]
    registry = tmp_path / "attribute_quarantine.json"
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "product_id": victim.pk,
                        "reason": "pending_research",
                        "added_at": "2026-10-06",
                        "added_by": "test",
                        "status": "active",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    call_command(
        "enrich_attributes", "--quarantine", str(registry), stdout=StringIO(), stderr=StringIO()
    )

    run = ImportRun.objects.get(source="enrich_attributes")
    assert run.stats["committed"] == len(drills) and run.stats["quarantined"] == 1
    assert run.stats["quarantine"]["product_ids"] == [victim.pk]
    engine = ProductAttributeValue.objects.exclude(attribute__slug="tool_type")
    assert not engine.filter(product=victim).exists()
    assert engine.filter(product=ordered[0]).exists() and engine.filter(product=ordered[2]).exists()


def test_flush_skips_unchanged_rows(drills):
    """Повторный прогон не переписывает attrs_cache товаров, у которых он не изменился."""
    from django.test.utils import CaptureQueriesContext

    call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())
    with CaptureQueriesContext(connection) as queries:
        call_command("enrich_attributes", stdout=StringIO(), stderr=StringIO())

    updates = [q["sql"] for q in queries if q["sql"].startswith('UPDATE "catalog_product"')]
    assert updates == []
