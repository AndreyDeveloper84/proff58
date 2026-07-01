# Полное ревью кодовой базы — 2026-07-01

## Резюме

**Объект ревью:** `origin/dev` на коммите `67a048fec6a9160471067454d8dc7141a4d2e640`.

**Вердикт:** текущую ветку нельзя считать готовой к production-запуску магазина. Обнаружены четыре блокирующих дефекта, затрагивающих доступ к чужим заказам, оплату, остатки и работоспособность storefront за Nginx. Кроме них есть существенные разрывы в удалении ПДн, аутентификации webhook MAX, B2B/доставке, уведомлениях, AI sourcing и frontend quality gate.

| Уровень | Количество | Смысл |
|---|---:|---|
| Blocker | 4 | Исправить до production/deploy или включения соответствующего контура |
| Major | 13 | Исправить до запуска затронутой функции; часть можно вести параллельно |
| Minor | 7 | Не блокирует пилот само по себе, но требует постановки в backlog |

Сильная сторона проекта — уже существующие границы приложений, серверный пересчёт цены, блокировки остатков, feature flags, fail-closed ключ 1С и заметно усиленная модель AI sourcing. Главная проблема сейчас не в отсутствии архитектуры, а в незамкнутых бизнес- и security-инвариантах между модулями.

## Методика и охват

Проверены:

- Django/DRF: `accounts`, `catalog`, `pricing`, `orders`, `payments`, `delivery`, `notifications`, `integration_max`, `sync_1c`, `ai`, CRM/content/reviews и общая конфигурация;
- Next.js storefront и BFF-маршруты;
- Nginx, Docker, Celery и GitHub Actions;
- модели, миграции, сервисы, API, permissions, throttling, сигналы и тесты;
- соответствие ключевых потоков `docs/design/tz-master.md` и зафиксированным бизнес-решениям.

Вендорные инструкции в `.claude/agent-library` и `.claude/skills-library` не рецензировались построчно как продуктовый код, но оценено их влияние на репозиторий и Docker context.

## Blocker

### B-01. Регистрация с чужим телефоном захватывает гостевые заказы

**Где:** `apps/accounts/api/views.py:58-75`, `apps/orders/services.py:421-426`.

Регистрация не подтверждает владение телефоном, сразу авторизует пользователя и вызывает `claim_guest_orders()`. Сервис привязывает к аккаунту все гостевые заказы с совпавшим `customer_phone`. Злоумышленник может зарегистрировать ещё не занятый номер жертвы и получить её историю заказов, адрес, контактные и B2B-данные.

**Исправление:** запретить claim до подтверждения телефона. Ввести OTP/verified-phone invariant, нормализовать номер и выполнять привязку только после успешной проверки владения. Для уже существующих гостевых заказов желательно подтверждать ещё и одноразовый order token либо явно инициировать claim пользователем.

**Обязательные тесты:** регистрация без OTP не привязывает заказ; подтверждённый номер привязывает только свои заказы; повторный/просроченный OTP; конкурентная регистрация; разные форматы одного номера.

### B-02. YooKassa webhook применяет непроверенный тип события

**Где:** `apps/payments/services.py:121-204`.

После повторного чтения платежа из API YooKassa заменяется только `payment_data`, а ветвление продолжает использовать `event_type` из входящего webhook. Не сверяются фактические `status`/`paid`, принадлежность платежа заказу и допустимость перехода состояния. Например, входящее `payment.succeeded` способно перевести локальный заказ в `paid`, даже если проверенный объект провайдера ещё не `succeeded`, при совпавших сумме и валюте.

**Исправление:** строить переход исключительно по проверенному объекту провайдера; проверять `id`, metadata/order id, `status`, `paid`, сумму, валюту и таблицу допустимых переходов. Входящий event использовать только как подсказку/аудит. До исправления сохранить production kill-switch.

**Обязательные тесты:** поддельный event при `pending`; succeeded с чужим order metadata; downgrade `succeeded -> canceled`; повтор webhook; рассинхрон суммы/валюты; сбой verify API.

### B-03. Резервы товара создаются, но не освобождаются

**Где:** `apps/orders/services.py:384-387`, `apps/orders/models.py:161`; release/expiry-пути в `apps/orders` отсутствуют.

При оформлении заказа `available_quantity` уменьшается, а `reserved_quantity` увеличивается. Поле `reserved_until` существует, но при создании заказа не заполняется; задачи или сервиса освобождения резерва для отменённого, просроченного или неоплаченного заказа нет. Незавершённые checkout постепенно обнулят доступный остаток навсегда.

**Исправление:** сделать единый идемпотентный state transition service для reserve/confirm/release; задавать TTL в момент заказа; добавить periodic janitor с `select_for_update`; освобождать резерв при cancel/payment-expired и подтверждать списание при оплате/1С. Чётко определить, кто является мастером `available` и `reserved` при синхронизации 1С.

**Обязательные тесты:** expiry, cancel, paid, двойной release, конкурентные checkout/janitor, повтор события оплаты, reconciliation с 1С.

### B-04. Nginx CSP блокирует Next.js storefront

**Где:** `docker/nginx/default.conf:35-44`, `docker/nginx/default.conf:105-109`.

На уровне всего `server` установлен `Content-Security-Policy: default-src 'none'`. Отдельного CSP для `location /` и `/_next/` нет, поэтому браузер блокирует JS, CSS, изображения и шрифты Next.js. Комментарий об override фронтендом не реализован; добавление второго CSP не отменило бы первый, а применило бы пересечение политик.

**Исправление:** вынести строгий `default-src 'none'` в API-only locations либо задать полноценную storefront CSP с nonce/hash-стратегией. Добавить smoke-тест развернутого Nginx: HTML загружается, `/_next/static/*` не блокируется, нет CSP violations.

## Major

### M-01. Stored XSS через JSON-LD товара

**Где:** `frontend/components/product/ProductJsonLd.tsx:46-49`.

`JSON.stringify()` передаётся в `dangerouslySetInnerHTML` без экранирования `<`. Значение вроде `</script><script>...</script>` в названии/описании товара закрывает JSON-LD script. Данные приходят из admin/1С/контентных источников, поэтому доверять им нельзя.

**Рекомендация:** сериализовать JSON-LD с заменой `<` на `\u003c` (и безопасной обработкой U+2028/U+2029) либо использовать проверенный serializer; добавить regression-тест с `</script>`.

### M-02. Удаление аккаунта оставляет ПДн в Profile

**Где:** `apps/accounts/api/views.py:192-220`, `apps/accounts/models.py:77-90`.

Удаляются данные из `User` и `Order`, но остаются `Profile.company_name`, ИНН, КПП, юридический адрес и данные согласия. Ответ API утверждает, что данные обезличены, хотя это не так.

**Рекомендация:** транзакционно очищать/удалять Profile и остальные user-owned сущности по формальной data map; отдельно определить обязательные сроки хранения бухгалтерских документов и основание обработки.

### M-03. Смена телефона и регистрация не защищают идентичность

**Где:** `apps/accounts/api/views.py:223-240`, `apps/accounts/api/serializers.py:18-28`, `config/settings/base.py:188-197`.

Телефон меняется без OTP на новый номер и без повторного подтверждения пароля. Пароль проверяется только на длину шесть символов, Django password validators не вызываются. Login/register используют общий лимит `200/min`, а не отдельные низкие scopes. Нормализации телефона нет.

**Рекомендация:** OTP на новый номер + re-auth для чувствительного действия; `validate_password`; canonical E.164; отдельные throttles для login/register/OTP с защитой от enumeration.

### M-04. MAX webhook работает fail-open

**Где:** `apps/integration_max/webhook.py:35-40`, `config/settings/base.py:214-217`.

При пустом `MAX_WEBHOOK_SECRET` любой запрос считается подлинным; сравнение секрета выполнено обычным `==`. Production settings не требуют секрет при включённой интеграции.

**Рекомендация:** fail-closed, `secrets.compare_digest`, обязательный secret при активном MAX, ограничение body/rate и тест конфигурационного отказа старта.

### M-05. Delivery существует отдельно от checkout и суммы заказа

**Где:** `apps/delivery/api.py`, `apps/delivery/services.py`, `apps/orders/api/serializers.py:174-175`, `apps/orders/services.py:338-407`, `apps/delivery/migrations/0002_default_zones.py:11-23`.

API доставки рассчитывает подсказку по переданному клиентом `cart_total`, но checkout принимает свободные строки `delivery_method/address`, не выбирает серверную зону и не включает доставку в `Order.total`. Начальные пороги 5 000/10 000 расходятся с решением «собственная доставка бесплатно от 7 000»; CDEK-путь отсутствует.

**Рекомендация:** серверный `DeliveryQuote`/zone id, пересчёт по серверной корзине внутри order transaction, snapshot тарифа в заказе, CDEK adapter для области и единый source of truth для порога.

### M-06. Реализация B2B расходится с принятым продуктовым контрактом

**Где:** `apps/pricing/services.py:99-105`, `apps/orders/services.py:304-325`, `docs/design/tz-master.md:16-18,31,101-102,124-127`.

Код выдаёт верифицированному B2B отдельную wholesale-цену, хотя ТЗ фиксирует единый ценник. Гостевой B2B-заказ принудительно превращается в B2C, поэтому гостевой запрос счёта невозможен. Выбор режима «с НДС/без НДС» в модели заказа/счёта отсутствует; сама формулировка ТЗ сейчас фиксирует только включённый НДС 20%, то есть бизнес-решение отражено неполно.

**Рекомендация:** сначала закрепить один непротиворечивый VAT-контракт с бухгалтерией (цена включает НДС, цена без НДС или два юридически допустимых режима), затем удалить wholesale-ветку из customer-facing price, разрешить гостевой invoice checkout с валидированными реквизитами и сохранять VAT snapshot в заказе/строках/счёте.

### M-07. Событие оплаты не доходит до подписчиков заказа

**Где:** `apps/payments/services.py:172-179`, `apps/integration_max/receivers.py:43-77`, `apps/analytics/receivers.py:9-30`.

Payments публикует `payment_succeeded`, а MAX/analytics/CRM подписаны на `order_paid`. В результате статусная подписка MAX и аналитика оплаты не запускаются.

**Рекомендация:** определить один доменный event и публиковать его после commit либо сделать явный bridge с идемпотентным event id; добавить integration-тест `webhook -> order paid -> MAX/analytics`.

### M-08. Идемпотентность уведомлений не выдерживает конкуренцию и crash-after-send

**Где:** `apps/notifications/services.py:45-57,104-107`, `apps/notifications/models.py:43-53`, `apps/notifications/tasks.py`.

Перед постановкой задачи проверяется только существующий `sent`-лог, уникального ограничения на key нет. Два процесса могут поставить одинаковые сообщения. Если worker отправил сообщение и упал до записи лога, retry отправит повторно.

**Рекомендация:** transactional outbox/claim row с partial unique constraint на непустой idempotency key, состояния queued/sending/sent/unknown и provider message id.

### M-09. AI sourcing не реализует заявленную семантику uncertain outcome

**Где:** `apps/ai/services.py:313-329,377-383`, `apps/ai/sourcing/sources/web_search.py:18`, `apps/ai/sourcing/sources/marketplace.py:12`.

Любое исключение адаптера считается definite `ERROR`, резерв снимается и следующий retry может повторить уже оплаченный запрос. Read timeout/разрыв после отправки должен вести в `UNKNOWN`. Persist findings и закрытие call выполняются раздельно, поэтому crash между ними может инициировать повторный вызов. Baseline атрибутов всегда равен `None`, что даст ложные конфликты при применении атрибутов. Зарегистрированные web/marketplace adapters пока `NotImplementedError`.

**Рекомендация:** typed exceptions definite/unknown, provider idempotency capability, атомарное сохранение reply+findings+call status, реальный EAV baseline и явный configuration error для незавершённых adapters. Использовать `timezone.localdate()` вместо `date.today()` для дневного бюджета.

### M-10. Первый GET wishlist может завершиться 500

**Где:** `apps/accounts/api/views.py:105-132`, `apps/accounts/wishlist.py:11`, `apps/accounts/apps.py`.

Модель `WishlistItem` вынесена из `models.py` и не импортируется при старте приложения. GET обращается к `request.user.wishlist` до lazy-import, который есть только в POST/DELETE. Тест сначала делает POST и тем самым скрывает дефект.

**Рекомендация:** перенести модель в стандартный models package либо импортировать её в app startup; добавить тест чистого GET сразу после login и `makemigrations --check` в CI.

### M-11. Account frontend не выполняет CSRF-контракт backend

**Где:** `apps/accounts/api/views.py:244-257`, `frontend/lib/auth.ts:32-36`, `frontend/app/account/profile/page.tsx:47`.

Backend требует предварительный GET `/api/account/csrf/` и заголовок `X-CSRFToken`, но frontend logout этого не делает. UI не ждёт результат и сразу уводит пользователя на главную, маскируя 403; session фактически может остаться активной.

**Рекомендация:** единый same-origin API client с CSRF bootstrap/header и обработкой ошибок; logout await до redirect; интеграционный browser/API тест.

### M-12. Frontend quality gate отсутствует и уже пропускает ошибки

**Где:** `.github/workflows/tests.yml`, `frontend/app/account/orders/page.tsx:26`, `frontend/app/account/wishlist/page.tsx:26`, `frontend/app/api/cart/items/[id]/route.ts:7,19`.

CI запускает только Python checks. На проверенном коммите `npm run lint` падает на двух ошибках `no-html-link-for-pages`; прямой `tsc --noEmit` падает на неопределённом `RouteContext`. Production build не контролируется обязательным check.

**Рекомендация:** отдельный CI job: `npm ci`, lint, `tsc --noEmit`/`next typegen`, unit tests и `next build`; сделать его required для merge в `dev`.

### M-13. Загрузчик изображений допускает SSRF и memory DoS

**Где:** `apps/catalog/image_pipeline.py:27-40`.

`requests.get(url)` следует redirect, не ограничивает scheme/host/private IP и загружает весь body до проверки 10 MB. Затем PIL открывает недоверенное изображение без явной политики decompression bombs. Admin/AI/интеграционный URL способен обратиться к внутренней сети или исчерпать память worker.

**Рекомендация:** allowlist HTTPS, DNS/IP validation до каждого redirect, streaming с Content-Length и hard cap, отдельный worker, Pillow limits и безопасный отказ.

## Minor

### m-01. Частичный refund помечает весь платёж и заказ как refunded

`apps/payments/services.py:207-228`: любой `amount` приводит к полному статусу `REFUNDED`; нет диапазона `0 < amount <= paid`, отдельной модели возврата и поддержки нескольких частичных возвратов. До открытия refund в UI требуется ledger/model Refund.

### m-02. Внешний вызов refund выполняется внутри DB transaction

`apps/payments/services.py:207-228`: сетевой запрос удерживает транзакцию и увеличивает риск lock contention/неоднозначного состояния. Нужна claim/outbox/reconciliation схема.

### m-03. Guest access token передаётся в query string без явного no-store

`apps/orders/api/views.py:265,283`: токен открывает заказ/счёт с ПДн и оказывается в browser history/access logs. Добавить `Cache-Control: no-store`, строгую Referrer-Policy, ротацию/TTL и по возможности обмен одноразового URL на HttpOnly session.

### m-04. Invalid-key трафик 1С не ограничен на фактическом edge

`apps/core/throttling.py:3-7` делегирует brute-force/DoS в Nginx, но `docker/nginx/default.conf` не содержит `limit_req` или IP allowlist. DRF throttle срабатывает после permission и защищает только запросы с валидным ключом.

### m-05. Список заказов пользователя не пагинируется

`apps/orders/api/views.py:228-234`: APIView сериализует все заказы и items. Для длительно живущего B2B-аккаунта это приведёт к растущему ответу; применить limit/cursor pagination.

### m-06. Upload-модели требуют единых validators

`content`/`reviews` используют изображения, но нет общего слоя проверки размера, MIME/magic bytes, декодирования и quarantine. До публичной загрузки переиспользовать безопасный upload service.

### m-07. Автоматический migrate встроен в startup web

`docker/entrypoint.prod.sh:9`: каждый старт web выполняет migrations. Для одного инстанса допустимо, но при rolling/multi-replica deploy и тяжёлых DDL это опасно. Вынести миграции в отдельный release step с backup/rollback runbook.

## Технический долг и архитектурные наблюдения

1. **События — декларативные, но не end-to-end.** Наличие `core.events` создаёт видимость контракта, однако publisher/subscriber names уже расходятся. Нужен реестр событий, payload schema, owner и integration tests.
2. **Order lifecycle размазан по orders/payments/1C.** Нет единой state machine для оплаты, резерва, отмены и синхронизации. Это источник B-02/B-03 и будущих гонок.
3. **B2B и delivery реализованы до финального доменного контракта.** Модели и UI уже закрепляют спорные решения, поэтому дальнейшая работа без ADR увеличит стоимость переделки.
4. **AI architecture стала существенно безопаснее**, но adapters и failure taxonomy не доведены до production. Включать sourcing следует по отдельным source flags после contract tests.
5. **Vendored agent tooling раздувает репозиторий и Docker context.** `.dockerignore` не исключает `.claude`, поэтому `COPY . .` может переносить в build context большую библиотеку непродуктовых материалов. Вынести её в отдельный repo/submodule/artifact либо исключить из image context.
6. **Крупные data snapshots хранятся в Git.** Например, `data/catalog_fixed.json` около 13 MB; это замедляет clone, архивирование и review. Для версионируемых fixtures нужен отдельный артефактный storage или Git LFS.
7. **Тесты местами подтверждают реализацию, а не инвариант.** Пример: wishlist test сначала импортирует модель через POST; B2B tests закрепляют wholesale и запрет guest B2B, которые расходятся с актуальными решениями.
8. **CI не является полным release gate.** Нет frontend job, migration drift check, dependency/security scan и развёрнутого Nginx smoke-теста.

## Что уже сделано хорошо

- цены и остатки пересчитываются на сервере; товары блокируются через `select_for_update` при checkout;
- 1С API fail-closed при пустом ключе, использует constant-time compare, limits и транзакции;
- production settings требуют `SECRET_KEY`/`ALLOWED_HOSTS`, включают secure cookies, HTTPS и HSTS;
- payment и AI-контуры имеют kill-switch/feature flags;
- guest order token генерируется криптографически случайно;
- AI sourcing уже содержит бюджетную резервацию, owner attempt, provider idempotency key, evidence и guarded application;
- backend `ruff check apps config` проходит на целевом коммите.

## План исправлений

### Этап 0 — остановить критические риски (до production)

1. Исправить B-01: verified phone перед claim; провести аудит уже привязанных guest orders.
2. Исправить B-02: verified provider state machine; оставить payments disabled до security regression tests.
3. Исправить B-03: reserve lifecycle + janitor + reconciliation с 1С.
4. Исправить B-04 и M-01; добавить Nginx/browser security smoke tests.

**Exit criteria:** четыре Blocker закрыты тестами; storefront работает за production Nginx; security review платежей пройден; двойной release/claim невозможен.

### Этап 1 — identity, privacy и интеграции

1. M-02/M-03/M-04: data deletion map, OTP/re-auth, fail-closed MAX.
2. M-07/M-08: единое payment/order event и transactional notification outbox.
3. M-13 и m-03/m-04: SSRF-safe image fetch, guest-token hardening, edge limits 1С.

### Этап 2 — согласовать commerce contract

1. ADR по B2B/VAT: единая цена, юридическая модель «с/без НДС», guest invoice flow.
2. ADR по delivery: Пенза от 7 000 бесплатно, область через CDEK, snapshot quote.
3. После ADR — миграции, API contract, checkout UI и end-to-end tests.

### Этап 3 — AI и надёжность платежей

1. Typed definite/unknown failures, atomic persistence и EAV baseline sourcing.
2. Provider contract tests и staged enablement каждого adapter.
3. Payment/refund ledger, claim/reconciliation и partial refund semantics.

### Этап 4 — quality gate и долг

1. Required frontend CI, migration drift, backend/frontend build matrix.
2. Integration suites: checkout/payment/reserve, MAX status, guest B2B invoice, delivery.
3. Исключить `.claude` и большие data snapshots из production context/repo history strategy.
4. Вынести production migrations в release job и оформить rollback runbook.

## Проверки и ограничения

| Проверка | Результат |
|---|---|
| `ruff check apps config` | passed |
| `npm.cmd run lint` | failed: 2 ошибки `no-html-link-for-pages` |
| `tsc --noEmit` | failed: 2 ошибки `Cannot find name 'RouteContext'` |
| `next build` | не завершился в отведённое окно и не дал диагностического вывода |
| `pytest` | не запущен полностью: локальному базовому `.venv` не хватало `django-jazzmin`; установка из lock requirements во временный env зависла |
| `makemigrations --check --dry-run` | заблокирован той же отсутствующей зависимостью |
| `black --check` | не завершился в отведённое окно; результат не интерпретировался как pass |
| GitHub Actions API | запрос завис без ответа; статус удалённого CI в выводы не включён |

Динамические ограничения не меняют подтверждённые findings: каждый Blocker воспроизводится по прямому control/data flow. После исправлений необходимо повторить полный test suite в штатном CI-окружении.

## Критерий готовности к повторному ревью

- все Blocker закрыты отдельными PR с regression tests;
- для каждого Major есть fix PR либо принятое ADR/задача с owner и сроком;
- backend tests, migration drift, frontend lint/typecheck/build и Nginx smoke зелёные;
- PR описывает риск, rollout/rollback и фактические test evidence;
- payments, MAX и sourcing включаются только отдельными флагами после проверки production secrets/configuration.
