"""Пакетный импорт 1С (#125B): классификация в памяти → bulk_create/bulk_update.

Зеркало построчного `use_cases.run_rows`, но запись идёт пачками:

  Фаза 1 (в памяти): по картам из #125A определяем new/update/conflict/skip, мутируем
  Product/цены/остатки в памяти, копим объекты.
  Фаза 2 (БД): bulk_create товаров → bulk_update товаров → bulk цены/остатки → bulk staging.

Инварианты сохранены (см. тесты apps/sync_1c): conflict, partial-failure, skip-unchanged-price,
идемпотентность, ручной контент, счётчики. На неожиданный сбой bulk-транзакции — fallback на
построчный путь (`use_cases.run_rows`), чтобы «одна плохая строка не валила батч».

bulk_create обходит Product.save()/сигналы, поэтому здесь явно: slug предзадаём
(`product_writer.build_slug_for_import`), `updated_at` ставим вручную, кэш дерева категорий
инвалидируем один раз в конце (post_save-сигнал при bulk не срабатывает).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.catalog import categorization
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Product
from apps.catalog.services import invalidate_category_tree_cache
from apps.core.events import EventSource, price_changed, product_created, product_updated

from . import matching, normalizers, pricing, product_writer, stock
from .matching import MatchStatus
from .models import NomenclatureStaging, StagingStatus, SyncLog

BATCH = 1000

# Поля Product для bulk_update: бизнес-поля + денормализованные timestamp'ы + updated_at
# (auto_now НЕ срабатывает при bulk_update — ставим вручную).
_PRODUCT_UPDATE_FIELDS = [
    *product_writer._TRACKED_FIELDS,
    "price_updated_at",
    "stock_updated_at",
    "updated_at",
]


@dataclass
class _Plan:
    """Накопитель фазы 1."""

    staging: list[NomenclatureStaging] = field(default_factory=list)
    new_products: list[Product] = field(default_factory=list)
    update_products: list[Product] = field(default_factory=list)
    price_changes: list[pricing.PriceChange] = field(default_factory=list)
    stock_plans: list[stock.StockPlan] = field(default_factory=list)
    new_items: list[tuple] = field(default_factory=list)  # (product, item) — для slug
    created_pids: list = field(default_factory=list)  # product объекты (pk после bulk_create)
    updated_events: list[tuple] = field(default_factory=list)  # (product, changed_fields)
    price_events: list[pricing.PriceChange] = field(default_factory=list)


def run_rows_bulk(
    raw_items: list[dict],
    *,
    sync_log: SyncLog | None,
    source_file: str,
    create_missing: bool,
    allow_basic_fields: bool,
    error_lines: list[str],
    result,
    tally_error,
) -> bool:
    """Выполнить пакетный импорт. Заполняет ``result``/``error_lines``.

    Возвращает True при успехе bulk-пути; False — если bulk-транзакция упала и вызывающий
    должен откатиться на построчный путь.
    """
    plan = _Plan()
    src = source_file or (sync_log.source_file if sync_log else "")

    # --- Фаза 1: классификация в памяти ---
    items = []  # нормализованные (для карт)
    parsed: list[tuple[dict, object]] = []
    for raw in raw_items:
        try:
            item = normalizers.normalize_item(raw)
            parsed.append((raw, item))
            items.append(item)
        except Exception:  # noqa: BLE001
            parsed.append((raw, None))

    maps = matching.build_match_maps(items)
    rules = categorization.load_active_rules()
    codes = {it.code_1c for it in items if it.code_1c}
    price_map = pricing.prefetch_current_prices(codes)

    for raw, item in parsed:
        staging = NomenclatureStaging(
            raw_payload=raw,
            row_hash=normalizers.row_hash(raw),
            sync_log=sync_log,
            source_file=src,
        )
        plan.staging.append(staging)

        if item is None:
            staging.status = StagingStatus.ERROR
            staging.error_message = "Ошибка нормализации строки"
            staging.processed_at = timezone.now()
            tally_error(result, error_lines, "—", staging.error_message)
            continue

        staging.code_1c = item.code_1c
        staging.article = item.article
        staging.name_1c = item.name
        staging.unit = item.unit
        staging.price = item.price
        staging.stock = item.stock
        staging.is_active_1c = item.is_active

        if not item.has_identifier:
            _row_error(staging, "Нет идентификатора (code_1c / article).")
            tally_error(result, error_lines, "—", staging.error_message)
            continue

        # Классификация одной строки изолирована: неожиданный сбой → строка в error,
        # остальные продолжаются (partial-failure на уровне фазы 1; ничего не аппендим до успеха).
        try:
            _classify_row(
                item,
                staging,
                maps,
                rules,
                price_map,
                plan,
                result,
                create_missing,
                allow_basic_fields,
                error_lines,
                tally_error,
            )
        except Exception:  # noqa: BLE001
            _row_error(staging, "Ошибка обработки строки")
            tally_error(
                result, error_lines, item.code_1c or item.article or "—", "ошибка обработки"
            )

    # --- Фаза 2: запись пачками (одна транзакция; при сбое — сигнал на fallback) ---
    try:
        with transaction.atomic():
            _assign_slugs(plan.new_items)
            if plan.new_products:
                Product.objects.bulk_create(plan.new_products, batch_size=BATCH)
            if plan.update_products:
                Product.objects.bulk_update(
                    plan.update_products, _PRODUCT_UPDATE_FIELDS, batch_size=BATCH
                )
            pricing.apply_prices_bulk(plan.price_changes, price_map, batch_size=BATCH)
            stock.apply_stock_bulk(plan.stock_plans, batch_size=BATCH)
            _save_staging(plan.staging)
            _register_events(plan)
            transaction.on_commit(invalidate_category_tree_cache)
            transaction.on_commit(invalidate_facets_cache)
    except Exception:  # noqa: BLE001
        return False  # bulk упал — вызывающий откатится на построчный путь
    return True


def _classify_row(
    item,
    staging,
    maps,
    rules,
    price_map,
    plan,
    result,
    create_missing,
    allow_basic_fields,
    error_lines,
    tally_error,
) -> None:
    """Классифицировать одну строку и накопить план (аппенды — только при полном успехе)."""
    match = matching.resolve_in_memory(item, maps)
    if match.status == MatchStatus.CONFLICT:
        _row_error(staging, match.reason)
        tally_error(result, error_lines, item.code_1c or item.article or "—", match.reason)
        return
    if match.status == MatchStatus.NEW and not create_missing:
        staging.status = StagingStatus.SKIPPED
        staging.processed_at = timezone.now()
        result.skipped += 1
        return

    if match.status == MatchStatus.NEW:
        category, rule = categorization.categorize(
            categorization.ProductHint(
                name=item.name,
                article=item.article,
                brand=item.brand,
                source_group=item.source_group,
            ),
            rules=rules,
        )
        product = product_writer.build_new_product(item, category=category, rule=rule, slug="")
        pc = pricing.plan_price(product, item, current=price_map)
        sp = stock.plan_stock(product, item)
        if pc:
            plan.price_changes.append(pc)
            if pc.price_event:
                plan.price_events.append(pc)
        if sp:
            plan.stock_plans.append(sp)
        plan.new_products.append(product)
        plan.new_items.append((product, item))
        plan.created_pids.append(product)
        staging.status = StagingStatus.MATCHED if category else StagingStatus.NEW
        staging.processed_at = timezone.now()
        staging._product_obj = product
        maps.register(product)
        result.created += 1
        if category is None:
            result.uncategorized += 1
        return

    # MATCHED
    product = match.product
    before = product_writer.snapshot(product)
    pc = pricing.plan_price(product, item, current=price_map)
    sp = stock.plan_stock(product, item)
    product_writer.apply_basic_fields(product, item, allow_basic_fields=allow_basic_fields)
    changed = [f for f in product_writer._TRACKED_FIELDS if before[f] != getattr(product, f)]
    product.updated_at = timezone.now()
    if pc:
        plan.price_changes.append(pc)
        if pc.price_event:
            plan.price_events.append(pc)
    if sp:
        plan.stock_plans.append(sp)
    plan.update_products.append(product)
    if changed:
        plan.updated_events.append((product, changed))
    staging.status = StagingStatus.MATCHED
    staging.processed_at = timezone.now()
    staging._product_obj = product
    result.updated += 1


def _row_error(staging: NomenclatureStaging, reason: str) -> None:
    staging.status = StagingStatus.ERROR
    staging.error_message = reason
    staging.processed_at = timezone.now()


def _assign_slugs(new_items: list[tuple]) -> None:
    """Предзадать уникальные slug новым товарам (seed занятых — 1 запрос)."""
    if not new_items:
        return
    bases = {product_writer.slug_base(item) for _, item in new_items}
    taken = set(Product.objects.filter(slug__in=bases).values_list("slug", flat=True))
    for product, item in new_items:
        product.slug = product_writer.build_slug_for_import(item, taken)


def _save_staging(staging_objs: list[NomenclatureStaging]) -> None:
    """Привязать товар к staging (после bulk_create появился pk) и сохранить пачкой."""
    for s in staging_objs:
        obj = getattr(s, "_product_obj", None)
        if obj is not None:
            s.product = obj
    NomenclatureStaging.objects.bulk_create(staging_objs, batch_size=BATCH)


def _register_events(plan: _Plan) -> None:
    """Запланировать доменные события после коммита (только реальные изменения)."""
    created = list(plan.created_pids)
    updated = list(plan.updated_events)
    prices = list(plan.price_events)

    def _emit():
        for product in created:
            product_created.send(sender=Product, product_id=product.pk, source=EventSource.ONE_C)
        for product, changed in updated:
            product_updated.send(
                sender=Product,
                product_id=product.pk,
                source=EventSource.ONE_C,
                changed_fields=changed,
            )
        for pc in prices:
            price_changed.send(
                sender=None,
                product_id=pc.product.pk,
                old_price=pc.old_price_for_event,
                new_price=pc.value,
                currency=pc.currency,
                source=EventSource.ONE_C,
            )

    transaction.on_commit(_emit)
