"""Подписчики событий для CRM-продаж.

Подключаются в AppConfig.ready() только при включённом feature flag `crm`.
"""

import logging

from apps.core import events

logger = logging.getLogger(__name__)


def _on_order_created(sender, order_id, **kwargs):
    logger.info("CRM sales: order_created received, order_id=%s (deal stub)", order_id)


def _on_order_paid(sender, order_id, **kwargs):
    logger.info("CRM sales: order_paid received, order_id=%s (deal stub)", order_id)


events.order_created.connect(_on_order_created, dispatch_uid="crm_sales_order_created")
events.order_paid.connect(_on_order_paid, dispatch_uid="crm_sales_order_paid")
