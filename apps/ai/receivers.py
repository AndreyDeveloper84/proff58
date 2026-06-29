# apps/ai/receivers.py
"""Подписка AI на доменные события (ARCHITECTURE-AI §5).

Подключается в AiConfig.ready() ТОЛЬКО под флагом ``ai``. Импортёр 1С эмит не
шлёт — 1С-товары идут батчем; подписка обслуживает admin/API-создание товаров.
"""
from __future__ import annotations

from django.db import transaction

from apps.core.events import product_created

from .tasks import enrich_product_task


def on_product_created(sender, product_id, **kwargs):
    transaction.on_commit(lambda: enrich_product_task.delay(product_id))


def connect():
    product_created.connect(on_product_created, dispatch_uid="ai.enrich.product_created")
