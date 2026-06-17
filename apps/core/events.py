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
  price_changed         — product_id, old_price, new_price

`order_*`, `payment_*`, `price_changed` пока без издателей — это контракт под
будущие модули orders/payments/pricing (#7/#8/#60).
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

# --- orders (контракт; издатель появится с #7) ---
order_created = Signal()
order_paid = Signal()
order_status_changed = Signal()

# --- payments (контракт; издатель появится с #8) ---
payment_succeeded = Signal()
payment_failed = Signal()

# --- pricing (контракт; издатель появится с #60) ---
price_changed = Signal()
