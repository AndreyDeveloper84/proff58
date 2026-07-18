# Runbook: MAX-уведомления (#521)

Эксплуатационный справочник по доставке уведомлений (#513–#518). Настройка
самого бота (токен, webhook, диплинк) — `docs/max-bot-setup.md`; этот документ —
про то, что делать, когда доставка ведёт себя не так.

## 1. Как устроена доставка (коротко)

```
domain event → apps.integration_max.receivers → notifications.create_notification()
  → Notification (intent, история в ЛК) → preference-check
  → NotificationLog (outbox) → Celery send_notification_task → MAX API
```

- **Notification** (`apps.notifications.models.Notification`) — то, что видит
  пользователь в истории/ЛК. `policy_skip_reason` — непусто, если preferences
  погасили отправку (`max_disabled`, `category_disabled:<category>`).
- **NotificationLog** (`apps.notifications.models.NotificationLog`) — техническая
  строка outbox одной попытки доставки. `status`: `queued → sending → sent |
  failed | unknown`. `error_kind` (только при `failed`, #521): `retryable`
  (429/5xx/сеть — Celery уже отретраил) или `permanent` (4xx — ретраить
  бессмысленно).

**Путь одного уведомления intent → delivery → provider result:** в админке
`/admin/notifications/notification/` найти intent по `event`/`idempotency_key`,
поле `delivery` ссылается на `NotificationLog` — там `status`/`error_kind`/
`error_message`/`updated_at`. Оба read-only (никогда не редактируются вручную —
только через код), кроме экшена retry ниже.

## 2. Метрики

`GET /metrics/notifications/` (Prometheus exposition; тот же `METRICS_TOKEN`,
что и `/metrics/`, если задан):

| Метрика | Смысл |
|---|---|
| `notification_delivery_total{status}` | строк outbox по статусу прямо сейчас |
| `notification_delivery_failed_total{error_kind}` | FAILED по классификации (retryable/permanent/unclassified) |
| `notification_queue_size` | сколько строк сейчас в `queued` |
| `notification_queue_lag_seconds` | возраст самой старой `queued`-строки — растёт, если воркер `celery` не забирает задачи |
| `notification_intent_skipped_total{reason}` | intent с policy-skip, по причине |
| `notification_intent_to_sent_seconds_avg` | средняя задержка intent → sent |

### Предлагаемые алерты (SLO-proposal — подключить в существующий Alertmanager/Grafana, конкретных правил в репо нет)

- **queue lag** — `notification_queue_lag_seconds > 600` (10 мин) и
  `notification_queue_size > 0` дольше 5 мин подряд → воркер `celery` не
  обрабатывает outbox (упал/не запущен/завис на чём-то другом).
- **рост failed** — `rate(notification_delivery_failed_total{error_kind="permanent"})`
  резко вырос → скорее всего массовая проблема конфигурации (напр. протух
  `MAX_BOT_TOKEN`), а не единичные заблокированные чаты.
- **retryable исчерпал retries** — `notification_delivery_total{status="failed"}`
  растёт вместе с `error_kind="retryable"` → MAX API деградирует (общий 5xx-шторм
  или rate-limit) — см. §4.

## 3. Классификация ошибок провайдера

`apps.notifications.channels.max.send_message()` поднимает:

- `MaxPermanentError` — 4xx кроме 429 (невалидный chat_id, бот заблокирован и
  т.п.). `send_notification_task` **не ретраит** — сразу `FAILED,
  error_kind=permanent`. Чинится вручную (см. §4) после устранения причины.
- `MaxRetryableError` — 429/5xx/сеть/таймаут. Ретраится Celery-задачей: если
  провайдер прислал `Retry-After` — используется он, иначе bounded
  backoff+jitter (`30s → 60s → 120s`, максимум 300s, `max_retries=3`).

## 4. Ручной retry (админка)

`/admin/notifications/notificationlog/` → выбрать строки → действие «Повторить
отправку (только retryable failed) — #521». Действие **игнорирует** выбранные
`permanent`-строки (не ретраит их, никакой опасности случайно зарезать чат
повторной отправкой заведомо некорректного запроса) и возвращает `queued`
retryable-строки на новый круг `send_notification_task`. Сообщение после
выполнения показывает, сколько поставлено и сколько пропущено.

## 5. Зависшая очередь (`queue_size` растёт, `queue_lag` растёт)

1. Проверить, что воркер `celery` жив: `docker compose ps celery` (или
   аналог на проде/staging — `docs/DEPLOY.md`).
2. Проверить логи воркера — задачи `send_notification_task` должны выполняться,
   не падать на импорте (`ModuleNotFoundError` после деплоя без пересборки образа
   — частая причина).
3. Если воркер жив, но очередь не двигается — проверить Redis
   (`CELERY_BROKER_URL`) доступен: `/healthz/` покажет 503, если Redis лежит.
4. `reconcile_stuck_notifications` (beat, каждые 10 мин) переводит зависшие в
   `sending` дольше 5 мин в `unknown` — это НЕ решение проблемы, а фиксация
   неопределённости (crash-after-send: возможно, реально ушло, возможно нет).
   `unknown` не ретраится автоматически — сверять вручную по логам MAX/жалобам.

## 6. Провайдер лежит (webhook/API outage)

- `retryable`-ошибки сами отретраятся (bounded backoff) — ничего делать не
  нужно, кроме мониторинга §2 «рост failed».
- Если outage длится дольше, чем `max_retries=3` × backoff (несколько минут) —
  строки уйдут в `failed/retryable`. После восстановления провайдера — массовый
  retry через админку (отфильтровать `status=failed`, `error_kind=retryable`
  по времени, выбрать все, применить действие).
- **Не трогать** `sync_1c`/`orders`/`payments` — сбой MAX не откатывает статус
  заказа/платежа/остаток (архитектурная гарантия, on_commit + try/except в
  receivers, см. #514/#516/#518).

## 7. Rollback / feature flag

- Бизнес-флаг `max_chat` (`SiteSettings.max_chat_enabled`, `apps.core.features`)
  — глобальный kill-switch. Выключение **не ломает** обработку заказов/остатков/
  платежей: домен-события продолжают публиковаться и создавать `Notification`
  (intent/история сохраняется), но `send()` пропускает доставку
  (`status=skipped`, "MAX канал недоступен или отключён") — audit trail цел.
- Runtime toggle применяется немедленно (#514: receivers подключены
  детерминированно, флаг проверяется в `send()` на каждый вызов, не при старте
  процесса) — рестарт не нужен.
- Откат кода (revert деплоя) safe — все миграции только добавляют поля/таблицы,
  ничего не удаляют.

## 8. Staged rollout

Механизм — существующий бизнес-флаг `max_chat` (нет отдельной инфраструктуры
когорт — не строили, т.к. не было явного требования сверх этого runbook):

1. **Dev/внутренние пользователи** — `max_chat_enabled=True` только на dev/staging
   (`dev.proff58.ru`), реальные MAX-боты только там (`docs/max-bot-setup.md` §7).
2. **Маленькая когорта на проде** — включить `max_chat_enabled=True` на проде,
   держать `MAX_BOT_TOKEN` реального прод-бота; наблюдать метрики §2 первые
   24–48 часов на реальном трафике перед объявлением фичи пользователям.
3. **Все сервисные уведомления** — after §2 стабилен (низкий `failed`, низкий
   `queue_lag`) — фича доступна всем зарегистрированным с привязкой MAX.
   `marketing_enabled` остаётся `False` по умолчанию весь rollout (#515) —
   отдельное решение, не часть этого этапирования.

## 9. Dev E2E smoke (перед staged rollout §8 и после значимых изменений)

```bash
# 1. MAX link — привязать тестовый аккаунт через /api/account/max/link/ (см. max-bot-setup.md §4.2, ngrok)
# 2. Заказ — создать заказ на сайте, подтвердить в 1С (demo_1c_orders) → проверить order_created/order_confirmed в истории
python manage.py demo_1c_orders --scenario shipped
# 3. Появление товара — обнулить available_quantity, подписаться через POST .../availability-subscription/,
#    затем прогнать stocks/update с available_stock>0 → проверить product_available в истории
# 4. История/read-state — GET /api/account/notifications/, unread-count/, POST .../read/
```

## 10. Retention

- `NOTIFICATION_LOG_RETENTION_DAYS` (default 90) — `NotificationLog` (содержит
  `text`/`chat_id`) в терминальном статусе (`sent/failed/skipped/unknown`)
  старше этого — удаляется (`cleanup_old_notification_logs`, beat, ночью).
  `QUEUED`/`SENDING` не трогает.
- `NOTIFICATION_RETENTION_DAYS` (default 365) — `Notification` (история в ЛК,
  без `chat_id`) старше — удаляется (`cleanup_old_notifications`, beat, ночью).
- Удаление `NotificationLog` не рвёт `Notification.delivery` (`on_delete=SET_NULL`)
  — история в ЛК не пропадает раньше своего retention, даже если outbox-лог уже
  вычищен.
