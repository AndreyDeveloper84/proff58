"""Матрица переходов оси обработки заказа (`fulfillment_status`).

Единственный источник правды о допустимых переходах по оси обработки —
строго по docs/order-lifecycle.md §7. Переиспользуется обменом с 1С
(apps.sync_1c.use_cases.confirm_orders) и любым будущим кодом смены статуса.

Правила:
- forward-only: статус движется только вперёд по бизнес-цепочке;
- cancel доступен из любого нетерминального статуса;
- идемпотентность: переход same→same всегда разрешён (no-op у вызывающего);
- терминальные статусы (completed/cancelled) переходов не имеют.
"""

from __future__ import annotations

from .models import FulfillmentStatus as FS

# Карта допустимых целевых статусов для каждого исходного (без same→same:
# идемпотентность проверяется отдельно, чтобы вызывающий мог сделать no-op).
_TRANSITIONS: dict[str, set[str]] = {
    FS.NEW: {FS.CONFIRMED, FS.CANCELLED},
    FS.CONFIRMED: {FS.ASSEMBLING, FS.READY, FS.CANCELLED},
    FS.ASSEMBLING: {FS.READY, FS.CANCELLED},
    FS.READY: {FS.SHIPPED, FS.COMPLETED, FS.CANCELLED},
    FS.SHIPPED: {FS.COMPLETED, FS.CANCELLED},
    FS.COMPLETED: set(),  # терминал
    FS.CANCELLED: set(),  # терминал
}


def can_transition(old: str, new: str) -> bool:
    """Допустим ли переход обработки old → new.

    same→same считается допустимым (идемпотентный повтор статуса). Решение,
    публиковать ли событие, принимает вызывающий (реальная смена ≠ no-op).
    """
    if old == new:
        return True
    return new in _TRANSITIONS.get(old, set())
