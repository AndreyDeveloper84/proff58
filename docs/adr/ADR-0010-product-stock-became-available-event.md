# ADR-0010: Доменное событие `product_stock_became_available`

- Статус: принято
- Дата: 2026-07-17
- Связано: #518, #517, #513, `apps/sync_1c/stock.py`, ADR-0009

## Контекст

#517 добавил `ProductAvailabilitySubscription` (user-owned one-shot подписка на
появление товара). #518 должен уведомить подписчиков MAX-ботом, когда 1С
подтверждает, что товар перешёл из отсутствия в наличие (`available_quantity`
`0 → positive`). Обмен с 1С — `apps.sync_1c` (единственное место, где
встречаются 1С и каталог, слой 4 в `ARCHITECTURE.md` §4); каталог про 1С не
знает, а MAX-уведомления живут в `apps.integration_max`/`apps.notifications`.
Прямая связка `sync_1c` → `integration_max` нарушила бы границу «издатель эмитит
факт, подписчики реагируют, издатель о них не знает».

Два write-path пишут остаток: построчный `update_stocks` (`_update_values` +
`stock.set_current_stock`) и bulk `update_stocks_bulk` (`stock.plan_stock` +
`Product.bulk_update` + `stock.apply_stock_bulk`). Оба должны детектировать
переход и публиковать одинаково — иначе поведение по фичи 1С-экспорта (обычный
vs bulk) расходится.

## Решение

Новый сигнал `product_stock_became_available` в `apps.core.events`:

```python
product_stock_became_available = Signal()
# payload: product_id, old_available, new_available, source, transition_id
```

Издатель — `apps.sync_1c.use_cases._apply_stock` (обёртка над
`stock.set_current_stock`, зеркало `_apply_price`/`price_changed`, ADR
негласно уже установлен прецедентом `price_changed`) для построчного пути и
эквивалентная детекция в `update_stocks_bulk` для bulk-пути. Эмит **только** при
реальном переходе `old_available <= 0 and new_available > 0` (не на каждое
обновление остатка/timestamp) и **только** через `transaction.on_commit` —
подписчик не должен увидеть незакоммиченный остаток.

`transition_id` — `uuid4` hex, сгенерированный один раз в месте эмита и
переданный неизменным аргументом в Celery-задачу fan-out
(`apps.integration_max.tasks.notify_product_available`, подписчик —
`apps.integration_max.receivers`). Стабилен НЕ потому что детерминированно
выводится из данных, а потому что зафиксирован один раз и одинаков при retry
самой Celery-задачи — это и даёт идемпотентность `create_notification()` по
`idempotency_key=f"stock-available-{transition_id}-{subscription_id}"` при
повторной попытке той же задачи (упала на середине fan-out → retry не
дублирует уже отправленные уведомления).

Подписчик (`apps.integration_max.receivers`) **не** делает fan-out синхронно в
обработчике сигнала (тот выполняется в потоке импорта/HTTP-запроса 1С сразу
после commit) — только `.delay()` на Celery-задачу. Сам fan-out (claim
подписок, батчи, создание Notification) — целиком в задаче.

## Последствия

**Плюсы:**
- `sync_1c` не знает о MAX/notifications — только публикует факт, как и
  `price_changed`/`order_status_changed`.
- Один и тот же контракт для обоих write-path — построчный и bulk импорт дают
  одинаковый результат (#518 AC).
- Тяжёлый fan-out гарантированно вне HTTP-запроса/sync-транзакции импорта.

**Минусы / компромиссы:**
- Ещё один сигнал в реестре `apps.core.events`.
- Row-wise и bulk путь детектируют переход независимым кодом (нет общей
  «одной функции» — `_update_values` и `update_stocks_bulk` устроены слишком
  по-разному, чтобы разделить один хелпер без потери их текущих оптимизаций
  по памяти/числу запросов); риск расхождения логики между ними при будущих
  правках — заметно комментариями с явной перекрёстной ссылкой.

**Риски:**
- Очень популярный товар с большим числом подписчиков — один Celery-таск на
  весь fan-out (внутри себя чанкует, но не расщепляется на под-таски). При
  реальном масштабе региональной витрины (не маркетплейс) это осознанно
  достаточно; настоящее разделение на под-таски по чанкам — если понадобится.
