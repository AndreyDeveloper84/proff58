# План: production-контур уведомлений в MAX

Дата: 2026-07-17  
Статус: Ready for implementation  
Epic: [#513](https://github.com/AndreyDeveloper84/proff58/issues/513)  
Приоритет: P0/P1  
Оценка MVP: 12–18 инженерных дней, критический путь 8–12 дней

## 1. Решение

Регистрацию не перепроектируем. В проекте уже существуют:

- регистрация и вход по телефону/паролю через Django session auth;
- logout и текущая пользовательская сессия;
- вход, регистрация, привязка и отвязка MAX через deeplink flow;
- MAX webhook;
- базовый notification outbox, Celery worker, retry и журнал доставки;
- доменные события заказа и часть MAX-уведомлений.

Работа начинается не с нового auth flow, а с исправления разрыва между
`MaxAccount` и доставкой уведомлений, после чего достраиваются:

1. пользовательские настройки и consent;
2. полная матрица уведомлений заказа;
3. подписка «Сообщить о поступлении»;
4. frontend UX;
5. наблюдаемость и staged rollout.

## 2. Product goal

Пользователь должен:

- один раз подключить MAX;
- понимать, какие категории сообщений включены;
- получать важные изменения заказа без дублей;
- подписаться на отсутствующий товар;
- получить сообщение после фактического появления товара по данным 1С;
- видеть историю уведомлений в личном кабинете;
- в любой момент отключить категорию или MAX целиком.

Для магазина основной business value первой версии:

- меньше ручных вопросов менеджеру о статусе заказа;
- возврат покупателя на PDP после появления товара;
- измеримая доставка сервисных сообщений;
- отсутствие рекламных сообщений без отдельного согласия.

## 3. Аудит текущего состояния

### 3.1 Регистрация и сессия

| Возможность | Состояние | Решение |
|---|---|---|
| Custom `User` | Реализовано | Не менять |
| Регистрация телефон + пароль | `POST /api/account/register/` | Не менять |
| Login/logout | Реализованы | Не менять |
| Refresh token | Не применяется: используется Django session | Не добавлять JWT ради уведомлений |
| MAX login/link/unlink/status | Реализованы в `apps.integration_max` | Переиспользовать |
| Password reset | Не найден | Отдельный auth follow-up, не блокирует #513 |
| Notification consent/preferences | Отсутствуют | Реализовать в #515 |

### 3.2 MAX integration

Есть:

- `MaxAccount` и `MaxAuthAttempt`;
- one-time deeplink, TTL и browser-session binding;
- webhook secret validation и дедупликация событий;
- link/unlink/status API;
- MAX provider с timeout;
- эксплуатационная задача
  [#496](https://github.com/AndreyDeveloper84/proff58/issues/496).

Критический дефект:

- новый flow сохраняет recipient в `MaxAccount.chat_id`;
- `notifications.send()` и order receivers читают legacy
  `User.max_chat_id`;
- профиль может показывать «MAX подключён», но уведомление не будет поставлено
  в очередь.

Дополнительный риск:

- order receivers подключаются в `AppConfig.ready()` только если business flag
  `max_chat` включён в момент старта;
- runtime-включение флага не гарантирует подключение receivers.

Это P0-задача
[#514](https://github.com/AndreyDeveloper84/proff58/issues/514).

### 3.3 Notification domain

Уже реализовано:

- `NotificationLog` как delivery/outbox;
- статусы `queued`, `sending`, `sent`, `failed`, `skipped`, `unknown`;
- DB idempotency constraint;
- Celery retry;
- защита от конкурентной повторной отправки;
- reconcile зависших `sending`;
- MAX provider;
- Django Admin и тесты.

Не реализовано:

- user-visible notification intent/history;
- `UserNotificationPreference`;
- read/unread state;
- preferences/history API;
- разделение service/availability/marketing policy;
- explicit marketing consent;
- сохранение provider message ID;
- классификация retryable/permanent provider errors;
- versioned template contract;
- retention policy и delivery metrics.

Вывод: Notification Core не надо создавать заново. Нужно эволюционно расширить
существующий outbox в задаче
[#515](https://github.com/AndreyDeveloper84/proff58/issues/515).

### 3.4 Заказы

Есть publishers:

- `order_created`;
- `order_paid`;
- `order_status_changed`;
- payment success/failure events.

Есть MAX receivers для:

- создания;
- оплаты;
- shipped;
- completed;
- generic status change.

Пробелы:

- recipient выбирается через legacy field;
- нет централизованной проверки preferences;
- тексты частично расходятся с `docs/order-lifecycle.md`;
- нет явной полной матрицы `confirmed`, `ready`, `cancelled`, `refunded`;
- нет пользовательской истории;
- promised guest CTA «Отслеживать в MAX» на thank-you page отсутствует.

Registered-user flow закрывается в
[#516](https://github.com/AndreyDeveloper84/proff58/issues/516). Guest flow
вынесен в P2
[#520](https://github.com/AndreyDeveloper84/proff58/issues/520), потому что он
требует отдельной защиты от захвата чужого заказа.

### 3.5 Поступление товара

Сейчас отсутствуют:

- модель подписки пользователя на товар;
- API subscribe/unsubscribe/status;
- событие `product_stock_became_available`;
- fan-out подписчикам;
- PDP CTA.

Остатки обновляются как минимум двумя путями:

- row-wise update через product writer;
- `update_stocks_bulk()` через `bulk_update`.

Bulk path не публикует per-product stock transition. Поэтому нельзя строить
availability delivery только на текущем `product_updated`: будут пропуски.

Модель/API реализуются в
[#517](https://github.com/AndreyDeveloper84/proff58/issues/517), stock transition
и fan-out — в
[#518](https://github.com/AndreyDeveloper84/proff58/issues/518).

### 3.6 Frontend

Есть:

- профиль;
- `MaxLinkCard`;
- MAX auth/link flow;
- PDP availability state;
- страницы заказов и thank-you page.

Нет:

- notification preferences;
- availability subscription CTA/state;
- notification center;
- guest order MAX tracking CTA.

Основной UX scope поставлен в
[#519](https://github.com/AndreyDeveloper84/proff58/issues/519).

## 4. Scope MVP

Входит:

- канонический MAX recipient;
- backfill/audit legacy `max_chat_id`;
- service notification после успешного подключения MAX;
- notification intent/history;
- delivery/outbox;
- preferences:
  - master MAX toggle;
  - order updates;
  - product availability;
  - marketing;
- отдельный explicit consent для marketing;
- order lifecycle notifications;
- one-shot availability subscription;
- stock transition `0 -> >0` после sync 1С;
- профиль, PDP CTA и notification center;
- retry policy, метрики, runbook и staged rollout.

Не входит:

- новая регистрация;
- замена session auth на JWT;
- email/SMS;
- MAX Mini App;
- браузерные push/WebSocket;
- массовые маркетинговые кампании;
- Admin-конструктор произвольных templates;
- автоматическое объединение аккаунтов;
- повторная availability-подписка без нового действия пользователя.

## 5. Целевая архитектура

```text
accounts / orders / payments / sync_1c
                  |
                  | domain event after commit
                  v
          apps.notifications
        Notification intent/history
                  |
        preference + consent policy
                  |
                  v
       NotificationLog delivery/outbox
                  |
               Celery
                  |
                  v
       MAX provider + MaxAccount recipient
                  |
       sent / failed / skipped / unknown
                  |
        metrics + admin + user history
```

Границы:

- domain-модули публикуют факт, но не вызывают MAX API;
- `apps.notifications` владеет policy, intent и delivery;
- `apps.integration_max` владеет внешней идентичностью MAX и webhook/auth;
- `apps.sync_1c` публикует stock transition, но не читает подписки;
- frontend не получает bot token, webhook secret или raw chat ID.

## 6. Модель данных

### 6.1 `UserNotificationPreference`

Предлагаемые поля:

| Поле | Default | Назначение |
|---|---:|---|
| `user` | — | OneToOne |
| `max_enabled` | `true` | Master switch после link |
| `order_updates_enabled` | `true` | Сервисные статусы заказа |
| `product_availability_enabled` | `true` | Разрешает individual subscriptions |
| `marketing_enabled` | `false` | Только explicit opt-in |
| `marketing_consent_at` | `null` | Аудит согласия |
| `marketing_consent_version` | `""` | Версия текста |
| timestamps | — | Аудит изменений |

Правила:

- регистрация не должна зависеть от marketing consent;
- `marketing_enabled` никогда не становится `true` автоматически;
- individual availability subscription остаётся отдельным явным действием;
- unlink MAX выключает фактическую доставку, но не стирает audit/history.

### 6.2 `Notification`

User-visible intent:

- `user`;
- `event`;
- `category`: `service`, `order`, `availability`, `marketing`;
- `title`, `body`;
- безопасный `data` snapshot;
- `idempotency_key`;
- `read_at`;
- timestamps.

Snapshot не должен содержать:

- bot/webhook token;
- raw provider payload;
- пароль/session key;
- guest access token;
- лишние телефон/e-mail.

### 6.3 `NotificationLog`

Существующую таблицу сохранить как delivery/outbox и добавить nullable FK на
`Notification`. Это безопаснее, чем rename/rewrite работающей таблицы.

Дополнительно:

- provider message ID;
- attempt/retry metadata;
- normalized failure code;
- timestamps отправки;
- индекс для operational queries.

### 6.4 `ProductAvailabilitySubscription`

Предлагаемые поля:

- `user`;
- `product`;
- `channel=max`;
- `status`: `active`, `queued`, `notified`, `cancelled`;
- `subscribed_at`, `queued_at`, `notified_at`, `cancelled_at`;
- ссылка на созданное Notification/delivery при наличии.

Инварианты:

- одна active subscription на `(user, product, channel)`;
- subscribe/unsubscribe идемпотентны;
- разрешён только опубликованный и отсутствующий товар;
- one-shot: после claim подписка не используется повторно;
- повторный интерес после следующего out-of-stock требует нового subscribe.

## 7. API contracts

Предлагаемые endpoints:

```text
GET   /api/account/notification-preferences/
PATCH /api/account/notification-preferences/

GET   /api/account/notifications/
GET   /api/account/notifications/unread-count/
POST  /api/account/notifications/<id>/read/
POST  /api/account/notifications/read-all/

GET    /api/products/<id>/availability-subscription/
POST   /api/products/<id>/availability-subscription/
DELETE /api/products/<id>/availability-subscription/
```

Основные machine-readable errors:

- `authentication_required`;
- `max_connection_required`;
- `notification_category_disabled`;
- `already_in_stock`;
- `product_not_available_for_subscription`;
- `rate_limited`;
- `conflict`.

Все account endpoints используют `IsAuthenticated` и фильтруют данные по
`request.user`. Product subscription endpoint не принимает `user_id` с клиента.

## 8. События и policy

### 8.1 Accounts/MAX

Не отправлять welcome на обычный `user_registered`, если MAX ещё не подключён:
событие будет потеряно как `skipped`.

Для MVP использовать committed business event успешного link:

```text
max_account_linked
  -> notification `max_connected`
  -> «MAX подключён. Здесь будут статусы заказов и выбранных товаров»
```

Повторный login уже связанного MAX не должен каждый раз слать welcome.

### 8.2 Orders/payments

Уведомлять:

- `order_created`;
- `fulfillment -> confirmed`;
- `fulfillment -> ready`;
- `fulfillment -> shipped`;
- `fulfillment -> completed`;
- `fulfillment -> cancelled`;
- `payment -> paid`;
- `payment -> refunded`.

Не уведомлять в MVP:

- `assembling`;
- технический `sync_1c_status`;
- no-op/replayed transition.

Idempotency:

```text
order:<order_id>:created
order:<order_id>:fulfillment:<new_status>
order:<order_id>:payment:<new_status>
```

### 8.3 Availability

Триггер:

```text
old_available <= 0 and new_available > 0
```

Алгоритм:

1. stock writer сохраняет старое и новое каноническое значение;
2. после commit публикуется stable transition ID;
3. Celery task выбирает active subscriptions батчами;
4. каждая subscription конкурентно claim-ится `active -> queued`;
5. создаются Notification + delivery;
6. duplicate import/worker не может claim-ить строку повторно;
7. ошибка MAX не откатывает остаток.

Bulk import не должен делать fan-out внутри транзакции или HTTP request.

## 9. Frontend states

### 9.1 Профиль

```text
Уведомления

[x] Статусы заказа
[x] Товары снова в наличии
[ ] Скидки и акции

MAX
● Подключён
[Отключить MAX]
```

Нужны состояния:

- loading;
- saved;
- save failed + retry;
- MAX disconnected;
- reconnect required;
- consent copy при включении marketing.

### 9.2 PDP

Для отсутствующего товара:

```text
Нет в наличии
[🔔 Сообщить о поступлении]
```

После subscribe:

```text
✓ Мы сообщим вам в MAX
[Отменить уведомление]
```

Разветвления:

- guest → login с return URL;
- authenticated, MAX disconnected → MAX link prompt;
- product уже появился → обновить состояние и показать buy CTA;
- duplicate click → тот же success state.

### 9.3 Notification center

```text
Уведомления

Сегодня
Заказ №123 подтверждён
14:30

Ранее
Товар снова появился в наличии
```

Нужны unread count, pagination, read/read-all, empty/loading/error states и
ссылки только на разрешённые user resources.

## 10. Backlog и зависимости

| Issue | Priority | Size | Owner area | Зависимости | Результат |
|---|---|---:|---|---|---|
| [#514](https://github.com/AndreyDeveloper84/proff58/issues/514) | P0 | M | backend/MAX | — | Канонический recipient, backfill, runtime-safe receivers |
| [#515](https://github.com/AndreyDeveloper84/proff58/issues/515) | P1 | L | backend | #514 | Preferences, intent/history, delivery API |
| [#516](https://github.com/AndreyDeveloper84/proff58/issues/516) | P1 | M | backend/orders | #514, #515 | Полная order/payment matrix |
| [#517](https://github.com/AndreyDeveloper84/proff58/issues/517) | P1 | M | backend/catalog | #514, #515 | Availability model и API |
| [#518](https://github.com/AndreyDeveloper84/proff58/issues/518) | P1 | L | backend/1C | #514, #515, #517 | Stock transition и fan-out |
| [#519](https://github.com/AndreyDeveloper84/proff58/issues/519) | P1 | L | frontend, ShiroPy | #514, #515, #517; E2E после #518 | Profile, PDP, history UX |
| [#521](https://github.com/AndreyDeveloper84/proff58/issues/521) | P1 | M | devops/backend | #514, #515 | Metrics, retry policy, runbook, rollout |
| [#520](https://github.com/AndreyDeveloper84/proff58/issues/520) | P2 | M | backend/frontend/security | #514, #515, #516, #519 | Guest order tracking |

GitHub не принял `ShiroPy` как assignee для #519: пользователь не доступен для
назначения в репозитории. В issue явно зафиксировано `Задача для: ShiroPy`.

## 11. Порядок реализации

### Wave 0 — delivery correctness

Только #514.

Gate:

- новый MAX link создаёт рабочий recipient;
- test send проходит через outbox;
- unlink прекращает доставку;
- legacy conflicts видимы и не затираются.

### Wave 1 — domain core

#515, затем базовая часть #521.

Gate:

- preferences/history API стабилен;
- service/marketing policy протестирована;
- delivery traceable;
- миграция additive и обратима.

### Wave 2 — business flows

Параллельно:

- #516 order notifications;
- #517 availability subscription.

После #517:

- #518 stock transition и fan-out.

### Wave 3 — UX

#519 можно начать после стабилизации API #515/#517:

1. profile + MAX/preferences;
2. PDP subscribe states;
3. notification center;
4. E2E с #516/#518.

### Wave 4 — rollout

Завершить #521:

1. dev internal users;
2. order notifications;
3. availability pilot на 10–20 товарах;
4. полный service rollout;
5. marketing остаётся выключенным.

P2 #520 выполнять после registered-user MVP.

## 12. Test strategy

### Backend

- migrations and constraints;
- ownership/permissions;
- preference policy;
- transaction rollback/on_commit;
- concurrent idempotency;
- provider retry classification;
- order transition matrix;
- row-wise и bulk stock transition;
- fan-out batching/query count;
- privacy regression.

Минимальные команды:

```bash
pytest apps/notifications apps/integration_max
pytest apps/orders apps/payments
pytest apps/sync_1c
python manage.py check
python manage.py makemigrations --check --dry-run
ruff check apps/notifications apps/integration_max apps/orders apps/sync_1c
```

### Frontend

```bash
npm test
npm run lint
npm run typecheck
```

Проверить:

- profile toggle states;
- PDP auth/MAX/subscribe branches;
- history pagination/read states;
- BFF error propagation;
- mobile/desktop;
- keyboard and screen reader labels.

### End-to-end

1. Создать пользователя через существующий login/password flow.
2. Подключить MAX.
3. Получить `max_connected`.
4. Оформить заказ.
5. Провести `confirmed -> ready -> completed`.
6. Проверить один delivery на переход.
7. Подписаться на отсутствующий товар.
8. Через test sync 1С провести `0 -> positive`.
9. Получить MAX message и history item.
10. Повторить callback/import и убедиться, что дубля нет.
11. Выключить category/master switch и проверить skipped policy.

## 13. Observability

Минимальные метрики:

- notification intents by event/category;
- deliveries by status and skip reason;
- MAX send latency;
- retry count;
- oldest queued age;
- failed/unknown count;
- availability subscribers/claimed/skipped;
- order notification dedupe count.

Не логировать:

- токены;
- webhook secret;
- session key;
- телефон/e-mail;
- полный chat ID;
- полный текст сообщения в обычном application log.

Допустимые correlation fields:

- notification ID;
- delivery ID;
- internal user/order/product ID;
- event;
- normalized provider status/error code.

## 14. Rollout и rollback

### Rollout

1. Применить additive migrations.
2. Выполнить dry-run audit/backfill MAX recipients.
3. Устранить конфликты.
4. Включить worker/beat и проверить queue health.
5. Включить feature для internal cohort.
6. Прогнать E2E.
7. Включить order category.
8. Включить availability pilot.
9. Расширить rollout.

### Rollback

- выключить создание новых MAX deliveries feature flag;
- не отключать publishers order/stock и не откатывать business commits;
- уже созданные queued delivery остановить/оставить согласно runbook;
- сохранить Notification/Delivery audit;
- additive columns/tables не удалять в emergency rollback;
- marketing всегда оставить disabled до отдельного решения.

## 15. Definition of Done MVP

- [ ] #514–#519 и #521 закрыты.
- [ ] #496 выполнена для dev environment.
- [ ] Регистрация не получила новый обязательный шаг.
- [ ] MAX recipient имеет один канонический источник.
- [ ] Preferences и consent работают на backend, а не только в UI.
- [ ] Order transitions доставляются идемпотентно.
- [ ] Availability работает для row-wise и bulk sync 1С.
- [ ] Пользователь может subscribe/unsubscribe/read.
- [ ] Нет cross-user access и утечки guest token/PII.
- [ ] Provider outage не ломает заказ, оплату или stock sync.
- [ ] Метрики, alert и runbook проверены.
- [ ] Dev E2E пройден с реальным MAX bot.

## 16. Follow-ups вне #513

- password reset/recovery для login/password;
- retention policy review с владельцем данных;
- email fallback;
- re-subscribe/re-arm availability policy;
- campaign/marketing domain;
- A/B и продуктовые метрики conversion после появления товара;
- закрытие legacy `User.max_chat_id` после периода совместимости.
