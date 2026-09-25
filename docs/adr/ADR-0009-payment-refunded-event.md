# ADR-0009: Доменное событие `payment_refunded`

- Статус: принято
- Дата: 2026-07-17
- Связано: #516, #513, `apps/payments/services.py::refund`, `docs/order-lifecycle.md` §3

## Контекст

`apps.payments.services.refund()` (#437) переводит `Payment`/`Order.payment_status`
в `partially_refunded`/`refunded`, но не публикует ни одного доменного события —
в отличие от успешной оплаты (`payment_succeeded`/`order_paid`, ЮKassa webhook) и
отказа (`payment_failed`). Из-за этого MAX-уведомление о возврате (§8
`docs/order-lifecycle.md`, #516) неоткуда было эмитить без прямой связки
`apps.payments` → `apps.integration_max`/`apps.notifications`, что нарушило бы
границу слоёв (`apps.core.events` — единственный контракт между «магазином» и
подписчиками, раздел 5 `docs/ARCHITECTURE.md`).

Переиспользовать `payment_failed` для возврата нельзя: подписчик (MAX-receiver,
аналитика) получил бы вводящее в заблуждение сообщение «оплата не прошла» вместо
«деньги возвращены» — разная семантика, разный текст уведомления.

## Решение

Завести новый сигнал `payment_refunded` в `apps.core.events` (единственное место
регистрации доменных сигналов, см. правило в шапке файла):

```python
payment_refunded = Signal()
# payload: payment_id, order_id, refund_id, amount: str, is_full: bool
```

Издатель — `apps.payments.services.refund()`, эмит через `transaction.on_commit`
после финализации `Refund`/`Payment`/`Order.payment_status` (тот же паттерн, что
`payment_succeeded`/`payment_failed`). `refund_id` — id строки `Refund` (ledger),
не `payment_id`: несколько частичных возвратов по одному платежу — отдельные
реальные события, не дубли друг друга (используется как часть idempotency_key
уведомления). `is_full` — различить текст «возврат выполнен» и «частичный
возврат» без повторного похода в БД подписчиком.

## Последствия

**Плюсы:**
- Подписчики (MAX-уведомления #516, будущая аналитика/CRM) реагируют на возврат
  так же, как на любое другое доменное событие — без прямой зависимости
  `apps.payments` от `apps.notifications`/`apps.integration_max`.
- Симметрично `payment_succeeded`/`payment_failed` — не новый паттерн, а
  достройка существующего контракта.

**Минусы / компромиссы:**
- Ещё один сигнал в реестре событий поддерживать при рефакторинге payments.

**Риски:**
- Частичные возвраты по одному платежу эмитят событие на каждый вызов
  `refund()` — если появится сценарий массовых частичных возвратов, подписчик
  должен сам решать, схлопывать ли уведомления (вне scope #516/MVP).
