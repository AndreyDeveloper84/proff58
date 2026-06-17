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

Payload каждого сигнала (kwargs у `.send()`):
  user_registered       — user
  b2b_verified          — user, organization
  product_created       — product, source                      # source: "1c" | "admin"
  product_updated       — product, source, changed_fields: list[str]
  order_created         — order
  order_paid            — order, payment
  order_status_changed  — order, old_status, new_status
  payment_succeeded     — payment, order
  payment_failed        — payment, order, reason
  price_changed         — product, old_price, new_price

`order_*`, `payment_*`, `price_changed` пока без издателей — это контракт под
будущие модули orders/payments/pricing (#7/#8/#60).
"""

from django.dispatch import Signal

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
