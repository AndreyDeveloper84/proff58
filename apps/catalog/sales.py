"""Продажи товаров и рейтинг «хитов» витрины.

Зачем модуль: блок «Хиты продаж» обязан опираться на факт продажи, а не на
новизну или ручной список. Здесь — единственная точка, где продажи попадают в
каталог и превращаются в рейтинг.

Источники фактов (``SalesSource``) равноправны и складываются:

- ``site`` — строки выполненных заказов сайта. Их публикует ``apps.orders``
  (каталог в чужие таблицы не ходит, ADR-0004), полностью пересчитывая окно на
  каждом прогоне: заказ мог быть отменён задним числом.
- ``1c`` — выгрузка продаж магазина через ``/api/1c/sales/upload``. Приходит
  порциями и накапливается, поэтому пересчёт сайта её не трогает.

Рейтинг (``ProductSalesStat``) — денормализация: сортировать витрину агрегатом
по фактам на каждый запрос нельзя. Строка появляется только у товара с
продажами за окно, поэтому «хитом» не станет товар, который не продавался.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Sum
from django.utils import timezone

from .filters import visible_products
from .models import ProductSalesFact, ProductSalesStat

__all__ = [
    "SalesRow",
    "bestsellers_queryset",
    "hit_product_ids",
    "record_sales_facts",
    "rebuild_sales_stats",
    "sales_window",
]


def _window_days() -> int:
    return int(getattr(settings, "SALES_WINDOW_DAYS", 90))


def _hit_top_n() -> int:
    return int(getattr(settings, "SALES_HIT_TOP_N", 24))


def _hit_min_quantity() -> Decimal:
    return Decimal(str(getattr(settings, "SALES_HIT_MIN_QUANTITY", 3)))


def sales_window(today: date | None = None) -> tuple[date, date]:
    """Границы скользящего окна рейтинга (включительно)."""
    end = today or timezone.localdate()
    return end - timedelta(days=_window_days() - 1), end


@dataclass(frozen=True)
class SalesRow:
    """Продажа одного товара за один день."""

    product_id: int
    date: date
    quantity: Decimal


@transaction.atomic
def record_sales_facts(
    source: str,
    rows: list[SalesRow],
    *,
    replace_window: tuple[date, date] | None = None,
) -> dict[str, int]:
    """Записать факты продаж одного источника.

    ``replace_window`` — режим полного пересчёта: факты источника за период
    сначала удаляются. Так работает сайт, где заказ мог быть отменён и продажу
    нужно снять. Без него (выгрузка 1С) строки апсертятся по ключу
    (товар, источник, день): повторная отправка того же дня перезаписывает
    количество, а не удваивает его.

    Нулевые и отрицательные количества отбрасываются: «продано 0» — это не факт
    продажи, а шум выгрузки (и нарушение check-constraint).
    """
    deleted = 0
    if replace_window is not None:
        since, until = replace_window
        deleted, _ = ProductSalesFact.objects.filter(
            source=source, date__gte=since, date__lte=until
        ).delete()

    payload = [row for row in rows if row.quantity > 0]
    if not payload:
        return {"written": 0, "skipped": len(rows), "deleted": deleted}

    ProductSalesFact.objects.bulk_create(
        [
            ProductSalesFact(
                product_id=row.product_id,
                source=source,
                date=row.date,
                quantity=row.quantity,
            )
            for row in payload
        ],
        update_conflicts=True,
        unique_fields=["product", "source", "date"],
        update_fields=["quantity", "updated_at"],
    )
    return {"written": len(payload), "skipped": len(rows) - len(payload), "deleted": deleted}


@transaction.atomic
def rebuild_sales_stats(today: date | None = None) -> dict[str, int]:
    """Пересобрать рейтинг продаж по фактам за окно.

    Полная замена таблицы: товар, выпавший из окна, обязан потерять и место, и
    бейдж «Хит» — инкрементальное обновление такие «вечные хиты» бы оставило.
    Читатели внутри транзакции видят прежний рейтинг до коммита.
    """
    since, until = sales_window(today)
    window = _window_days()
    top_n = _hit_top_n()
    min_qty = _hit_min_quantity()

    aggregated = (
        ProductSalesFact.objects.filter(date__gte=since, date__lte=until)
        .values("product_id")
        .annotate(
            quantity=Sum("quantity"),
            days_with_sales=Count("date", distinct=True),
            last_sold_on=Max("date"),
        )
        # product_id вторым ключом — детерминированный порядок при равных продажах,
        # иначе места и бейджи «плавали» бы между пересчётами.
        .order_by("-quantity", "product_id")
    )

    stats = []
    hits = 0
    for rank, row in enumerate(aggregated, start=1):
        # Хит — топ рейтинга И достаточный объём: с одной проданной штукой
        # товар может оказаться в топе на пустой статистике.
        is_hit = rank <= top_n and row["quantity"] >= min_qty
        hits += int(is_hit)
        stats.append(
            ProductSalesStat(
                product_id=row["product_id"],
                quantity=row["quantity"],
                days_with_sales=row["days_with_sales"],
                window_days=window,
                rank=rank,
                is_hit=is_hit,
                last_sold_on=row["last_sold_on"],
            )
        )

    ProductSalesStat.objects.all().delete()
    ProductSalesStat.objects.bulk_create(stats, batch_size=1000)
    return {"products": len(stats), "hits": hits, "window_days": window}


def purge_old_sales_facts(today: date | None = None) -> int:
    """Удалить факты, вышедшие за двойное окно (хвост для сверки, не для витрины)."""
    since, _ = sales_window(today)
    cutoff = since - timedelta(days=_window_days())
    deleted, _ = ProductSalesFact.objects.filter(date__lt=cutoff).delete()
    return deleted


def bestsellers_queryset():
    """Товары витрины с реальными продажами за окно, по убыванию продаж.

    Только опубликованные и только со строкой рейтинга: пустая выдача здесь —
    честный ответ «продаж пока нет», а не повод подставить что-то похожее.
    Без среза — размер выдачи задаёт пагинация вызывающего.
    """
    return visible_products().filter(sales_stat__isnull=False).order_by("sales_stat__rank")


def hit_product_ids(product_ids) -> set[int]:
    """Из переданных товаров — те, что помечены хитом (для бейджей на карточках)."""
    return set(
        ProductSalesStat.objects.filter(product_id__in=list(product_ids), is_hit=True).values_list(
            "product_id", flat=True
        )
    )
