"""Celery-задачи, инициируемые доменными событиями каталога/1С (#518).

Тяжёлый fan-out по подписчикам живёт здесь, а не в receivers.py: обработчик
сигнала (receivers.py) выполняется синхронно сразу после commit транзакции
импорта/HTTP-запроса 1С — там нельзя итерировать потенциально сотни подписчиков
(AC #518: "large fan-out не выполняется внутри HTTP request/sync transaction").
Receiver только валидирует и ставит .delay(); вся работа — здесь, в воркере.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Чанк обработки подписчиков внутри задачи (AC #518: "батчами") — не отдельные
# под-таски (см. ADR-0010 «Риски»): для масштаба региональной витрины избыточно.
_FANOUT_CHUNK = 200


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def notify_product_available(
    self, product_id: int, transition_id: str, old_available, new_available, source: str = ""
):
    """Уведомить всех активных подписчиков товара о появлении в наличии.

    Идемпотентно к retry самой задачи: `transition_id` фиксирован издателем
    (ADR-0010) и не меняется между попытками — `create_notification()` по
    idempotency_key пропустит подписки, уже обработанные в предыдущей попытке.
    Идемпотентно к повторному fan-out (дубль доставки Celery/повторный сигнал):
    `claim_active_subscriptions` — select_for_update(skip_locked=True), см.
    `apps.catalog.availability_subscriptions`.
    """
    from apps.catalog.availability_subscriptions import (
        claim_active_subscriptions,
        get_product_snapshot,
        mark_notified_bulk,
        revert_to_active,
    )
    from apps.notifications.services import create_notification

    product = get_product_snapshot(product_id)
    if product is None:
        logger.warning(
            "notify_product_available: product=%s not found (transition=%s)",
            product_id,
            transition_id,
        )
        return

    claimed = claim_active_subscriptions(product_id)
    subscriber_count = len(claimed)
    if not subscriber_count:
        logger.info(
            "notify_product_available: product=%s transition=%s subscribers=0",
            product_id,
            transition_id,
        )
        return

    price_note = f" Цена: {product.price} ₽." if product.price else ""
    payload = {"product_name": product.name, "price_note": price_note}

    notified = skipped = failed = 0
    for start in range(0, subscriber_count, _FANOUT_CHUNK):
        chunk_notified_ids: list[int] = []
        chunk_failed_ids: list[int] = []
        for sub in claimed[start : start + _FANOUT_CHUNK]:
            try:
                intent = create_notification(
                    user=sub.user,
                    event="product_available",
                    payload=payload,
                    idempotency_key=f"stock-available-{transition_id}-{sub.pk}",
                )
            except Exception:
                failed += 1
                chunk_failed_ids.append(sub.pk)
                logger.exception("notify_product_available: subscription=%s failed", sub.pk)
                continue
            # one-shot: подписка отработана независимо от policy-skip/чат не
            # найден — второй раз на следующий импорт остатков её не шлём.
            chunk_notified_ids.append(sub.pk)
            if intent is not None and intent.policy_skip_reason:
                skipped += 1
            else:
                notified += 1

        if chunk_notified_ids:
            mark_notified_bulk(chunk_notified_ids)
        if chunk_failed_ids:
            # #521: транзиентная ошибка — не оставляем подписку зависшей в
            # queued навсегда, возвращаем в active под следующий claim.
            revert_to_active(chunk_failed_ids)

    logger.info(
        "notify_product_available: product=%s transition=%s subscribers=%d notified=%d "
        "skipped=%d failed=%d",
        product_id,
        transition_id,
        subscriber_count,
        notified,
        skipped,
        failed,
    )
