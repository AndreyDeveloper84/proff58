"""Подписчики событий для CRM-задач.

Подключаются в AppConfig.ready() только при включённом feature flag `crm`.
"""

import logging

from apps.core import events

logger = logging.getLogger(__name__)


def _on_order_status_changed(sender, order_id, old_status, new_status, **kwargs):
    logger.info(
        "CRM tasks: order_status_changed order_id=%s %s→%s (task stub)",
        order_id,
        old_status,
        new_status,
    )


events.order_status_changed.connect(_on_order_status_changed)
