"""Конфигурация Celery.

Воркер и beat обслуживают фоновые задачи: обмен ценами/остатками с 1С,
конвейер обогащения каталога, отправку SMS и т.п.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("proff58")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Регулярные задачи (beat). Janitor зависших импортов 1С (#57): помечает прогоны,
# зависшие в RUNNING (умерший воркер), как ERROR — иначе они висят навсегда.
app.conf.beat_schedule = {
    "mark-stale-syncs": {
        "task": "apps.sync_1c.tasks.mark_stale_syncs",
        "schedule": 5 * 60,  # каждые 5 минут
    },
    "source-catalog-nightly": {
        "task": "apps.ai.tasks.batch_source_task",
        "schedule": crontab(hour=3, minute=30),  # ночью, после обмена с 1С
        "kwargs": {"limit": 200},
    },
    # #423 (B-03): освобождение просроченного резерва неоплаченных заказов.
    "release-expired-reservations": {
        "task": "apps.orders.tasks.release_expired_reservations",
        "schedule": 10 * 60,  # каждые 10 минут
    },
    # #559 (эпик #557): истечение B2B-счетов 24ч → отмена заказа + снятие резерва.
    "expire-b2b-invoices": {
        "task": "apps.orders.tasks.expire_b2b_invoices",
        "schedule": 10 * 60,  # каждые 10 минут
    },
    # DRF-952: онлайн-заказ не оплатили за 30 минут → отмена + возврат товара.
    # Каждые 5 минут, а не 10: резерв всего полчаса, и лишние 10 минут ожидания —
    # это 30% срока, в течение которых товар недоступен уже без причины.
    # Перед отменой задача спрашивает кассу — вебхук мог не дойти.
    "expire-unpaid-online-orders": {
        "task": "apps.payments.tasks.expire_unpaid_online_orders",
        "schedule": 5 * 60,
    },
    # #432 (M-09): зависшие RUNNING-прогоны sourcing → run=error, call=unknown
    # (резерв удержан до ручной сверки в админке «Вызовы внешних источников»).
    # Janitor существовал, но в beat не стоял — зависших никто не добивал.
    "mark-stale-sourcing-runs": {
        "task": "apps.ai.tasks.mark_stale_sourcing_runs",
        "schedule": 10 * 60,  # каждые 10 минут
    },
    # #432: гигиена ПДн/объёма — чистка raw_excerpt старше 30 дней.
    "purge-sourcing-excerpts": {
        "task": "apps.ai.tasks.purge_sourcing_excerpts",
        "schedule": 24 * 3600,  # раз в сутки
    },
    # #431 (M-08): сверка «зависших» в SENDING уведомлений (crash-after-send).
    "reconcile-stuck-notifications": {
        "task": "apps.notifications.tasks.reconcile_stuck_notifications",
        "schedule": 10 * 60,  # каждые 10 минут
    },
    # #521: retention policy — чистка старых outbox-логов/истории уведомлений.
    "cleanup-old-notification-logs": {
        "task": "apps.notifications.tasks.cleanup_old_notification_logs",
        "schedule": crontab(hour=4, minute=0),  # ночью
    },
    "cleanup-old-notifications": {
        "task": "apps.notifications.tasks.cleanup_old_notifications",
        "schedule": crontab(hour=4, minute=15),
    },
    # «Хиты продаж»: сначала заказы сайта отдают свои продажи в каталог, затем
    # каталог пересобирает рейтинг — уже с учётом и выгрузки 1С за сутки.
    # Порядок держим разносом по времени: задачи независимы, общий результат
    # даёт следующий прогон, поэтому гонка ничего не портит.
    "publish-sales-facts": {
        "task": "apps.orders.tasks.publish_sales_facts",
        "schedule": crontab(hour=4, minute=30),
    },
    "rebuild-sales-stats": {
        "task": "apps.catalog.tasks.rebuild_sales_stats",
        "schedule": crontab(hour=4, minute=45),
    },
    "purge-old-sales-facts": {
        "task": "apps.catalog.tasks.purge_old_sales_facts",
        "schedule": crontab(hour=5, minute=0),
    },
}
