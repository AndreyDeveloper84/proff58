"""Реестр доменных событий платформы — единый контракт.

Все доменные сигналы объявляются ТОЛЬКО здесь. Это публичный контракт событий:
издатель эмитит факт, подписчики реагируют, издатель о них не знает (ARCHITECTURE
раздел 5).

Правила:
- Новый доменный сигнал заводится только в этом файле и только вместе с ADR.
- Эмит — из сервисного слоя (use-case) или admin-flow, НЕ через `model.post_save`:
  иначе события дублируются и теряют контекст (`source`/`changed_fields`).
- Эмит выполняется через `transaction.on_commit(...)`, чтобы подписчик видел
  закоммиченные данные.
- Обработчики живут в `receivers.py` приложения-подписчика и подключаются в
  `AppConfig.ready()` (под feature-флагом для опциональных модулей — см. #59).

Payload каждого сигнала (kwargs у `.send()`) — стабильные идентификаторы и
снапшоты, НЕ живые ORM-инстансы. Подписчик при необходимости перечитывает объект
из БД (надёжно под Celery/несколькими воркерами — инстанс может устареть):
  user_registered       — user_id
  b2b_verified          — user_id, organization_id
  product_created       — product_id, source                   # source: EventSource
  product_updated       — product_id, source, changed_fields: list[str]
  order_created         — order_id
  order_paid            — order_id, payment_id
  order_status_changed  — order_id, old_status, new_status
  payment_succeeded     — payment_id, order_id
  payment_failed        — payment_id, order_id, reason
  payment_refunded      — payment_id, order_id, refund_id, amount: str, is_full: bool
  price_changed         — product_id, old_price, new_price, currency, source
  product_stock_became_available
                        — product_id, old_available: str, new_available: str, source, transition_id

`order_created` уже имеет издателя — `apps.orders.services.place_order` (#26).
`order_status_changed` — издатель `apps.sync_1c.use_cases.confirm_orders` (#50):
эмитится при реальной смене `fulfillment_status` по подтверждению из 1С.
`order_paid`/`payment_succeeded`/`payment_failed` — издатель ЮKassa-webhook
(`apps.payments.services.handle_webhook`, #431/M-07). `payment_refunded` —
издатель `apps.payments.services.refund()` (ADR-0009, #516). `price_changed`
пока без издателя — контракт под будущий модуль pricing (#60).
`product_stock_became_available` — издатель `apps.sync_1c.use_cases` (row-wise
`_apply_stock` и bulk `update_stocks_bulk`), только при реальном переходе
`old_available <= 0 → new_available > 0` (ADR-0010, #518).
"""

from django.dispatch import Signal


class EventSource:
    """Допустимые значения `source` в событиях — в одном месте, чтобы не расползлось
    (`"1c"`/`"1C"`/`"sync_1c"`/...)."""

    ADMIN = "admin"  # ручное изменение через админку
    ONE_C = "1c"  # импорт/обмен с 1С
    SYSTEM = "system"  # фоновые задачи/системные процессы
    API = "api"  # публичный/внешний API


# --- accounts ---
user_registered = Signal()
b2b_verified = Signal()

# --- catalog ---
product_created = Signal()
product_updated = Signal()
# product_stock_became_available — издатель apps.sync_1c.use_cases (ADR-0010, #518).
product_stock_became_available = Signal()

# --- orders ---
# order_created — издатель `apps.orders.services.place_order` (#26);
# order_status_changed — издатель `apps.sync_1c.use_cases.confirm_orders` (#50);
# order_paid — контракт под #8.
order_created = Signal()
order_paid = Signal()
order_status_changed = Signal()

# --- leads ---
# product_inquiry_created — издатель apps.leads.services.create_inquiry.
# payload: inquiry_id, kind, product_id
product_inquiry_created = Signal()

# --- payments ---
# payment_succeeded/payment_failed — издатель apps.payments.services.handle_webhook;
# payment_refunded — издатель apps.payments.services.refund() (ADR-0009, #516).
payment_succeeded = Signal()
payment_failed = Signal()
payment_refunded = Signal()

# --- pricing (контракт; издатель появится с #60) ---
price_changed = Signal()
