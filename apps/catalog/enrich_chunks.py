"""Запись результатов обогащения каталога частями (DRF-2738).

``enrich_attributes`` и ``enrich_tool_type`` раньше держали одну транзакцию на весь
прогон: замки строк ``catalog_product`` и PAV жили десятки минут, обмен с 1С и
админка ждали, а сбой на последней тысяче откатывал всё. Теперь единица работы —
чанк из :data:`CHUNK_PRODUCTS` товаров: решения принимаются без транзакции, запись
чанка идёт одной короткой транзакцией, после неё блокировки сняты.

Что гарантируется:

- записанные чанки остаются при любом сбое; обе команды идемпотентны, повторный
  запуск доводит дело; ``ImportRun.stats["committed"]`` — сколько товаров записано
  (обновляется внутри транзакции чанка, поэтому верен даже при kill);
- PAV и ``attrs_cache`` одного товара коммитятся вместе — чанк режется по товарам;
- порядок обработки прежний: как ``Product.Meta.ordering`` (``name``), плюс ``id``
  для одинаковых имён — отчёт dry-run не зависит от размера чанка;
- замки берутся в порядке «товары чанка по id → PAV», как в остальном проекте;
- две копии пишущего прогона одновременно не идут (advisory lock).
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.utils import timezone

from apps.catalog.models import ImportRun, ImportRunStatus, Product

logger = logging.getLogger(__name__)

#: Общий ключ замка для обеих команд: раньше их взаимно сериализовали замки строк на
#: весь прогон; enrich_attributes строит карту типов один раз в начале, и параллельный
#: enrich_tool_type менял бы типы под ним.
WRITE_LOCK_NAME = "catalog_enrich"

#: Размер чанка по товарам. Отдельно от размера SQL-пачки: ограниченные прогоны
#: (десятки–сотни товаров) умещаются в один чанк и остаются «всё или ничего».
CHUNK_PRODUCTS = 500


def ordered_ids(queryset) -> list[int]:
    """Порядок обработки: как у ``Product.Meta.ordering``, однозначный на дублях имён."""
    return list(queryset.order_by("name", "id").values_list("id", flat=True))


def iter_chunks(ids: list[int], size: int) -> Iterator[list[int]]:
    for start in range(0, len(ids), size):
        yield ids[start : start + size]


def load_chunk(queryset, chunk_ids: list[int]) -> list[Product]:
    """Товары чанка в порядке списка id. ``queryset`` несёт фильтры команды: товар,
    выпавший из выборки между листингом и чтением (удалена категория, снят с
    продажи), в чанк не попадает — а не роняет прогон."""
    by_id = queryset.filter(id__in=chunk_ids).order_by().in_bulk()
    return [by_id[pk] for pk in chunk_ids if pk in by_id]


def lock_products(ids: Iterable[int]) -> None:
    """Первый оператор транзакции записи: замки строк товаров по id.

    ``NO KEY UPDATE`` — вставкам со ссылкой на товар (корзина, строка заказа, цена)
    замок не мешает; с чекаутом и обменом 1С взаимное исключение сохраняется.
    """
    list(
        Product.objects.select_for_update(no_key=True)
        .filter(id__in=list(ids))
        .order_by("id")
        .values_list("id", flat=True)
    )


def record_progress(run: ImportRun | None, stats: dict, chunk_ids: list[int]) -> dict:
    """Зафиксировать прогресс ВНУТРИ транзакции чанка. Возвращает снимок stats.

    ``committed`` — товары записанных чанков по листингу (товар, выпавший из выборки
    между листингом и чтением, тоже считается: его чанк записан); ``last_product_id``
    — последний id чанка в порядке обработки (по имени), а не курсор.
    """
    stats["committed"] = stats.get("committed", 0) + len(chunk_ids)
    stats["last_product_id"] = chunk_ids[-1]
    snapshot = copy.deepcopy(stats)
    if run is not None:
        ImportRun.objects.filter(pk=run.pk).update(stats=snapshot)
    return snapshot


def finish_failed(
    run: ImportRun | None,
    committed_stats: dict,
    exc: BaseException,
    *,
    live_stats: dict | None = None,
) -> None:
    """Прогон прерван: статус FAILED, счётчики — на момент последнего коммита.

    ``live_stats`` — для того, что живёт вне транзакций чанков и остаётся при откате:
    опции tool_type, созданные из манифеста по ходу прогона (rollback-map обязан их знать).
    """
    if run is None:
        return
    stats = dict(committed_stats)
    if live_stats and live_stats.get("created_options"):
        stats["created_options"] = list(live_stats["created_options"])
    stats["error"] = str(exc) or exc.__class__.__name__
    if isinstance(exc, KeyboardInterrupt):
        stats["interrupted"] = True
    try:
        ImportRun.objects.filter(pk=run.pk).update(
            status=ImportRunStatus.FAILED, finished_at=timezone.now(), stats=stats
        )
    except DatabaseError:
        # Соединение потеряно: исходное исключение важнее, чем запись статуса.
        logger.exception("ImportRun %s: не удалось записать статус FAILED", run.pk)


def partial_write_hint(stats: dict) -> str:
    """Хвост сообщения об ошибке в режиме записи: что уже записано и что делать."""
    return (
        f" Записано товаров до сбоя: {stats.get('committed', 0)} — они остаются; "
        "после исправления повторный запуск идемпотентен и доведёт дело."
    )


@contextmanager
def exclusive_run(name: str):
    """Сессионный advisory lock: вторая копия пишущего прогона не стартует.

    С записью частями две копии чередовались бы и падали на уникальности PAV с
    частичной записью. Ключ — хэш имени команды, на время соединения.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [name])
        acquired = cur.fetchone()[0]
    if not acquired:
        raise CommandError(f"{name}: уже идёт другой пишущий прогон — дождитесь его.")
    try:
        yield
    finally:
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])
        except DatabaseError:
            logger.exception("%s: не удалось снять advisory lock (соединение потеряно?)", name)


__all__ = [
    "CHUNK_PRODUCTS",
    "exclusive_run",
    "finish_failed",
    "iter_chunks",
    "load_chunk",
    "lock_products",
    "ordered_ids",
    "partial_write_hint",
    "record_progress",
    "WRITE_LOCK_NAME",
]
