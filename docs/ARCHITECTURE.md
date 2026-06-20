# Архитектура платформы «Профессионал»

Спецификация модульной структуры и контрактов между приложениями.
Стек: Django + DRF · PostgreSQL · Celery + Redis. Цель — построить интернет-магазин «Профессионал»,
заложив в архитектуру рост в CRM, AI и модульную платформу **без переделок**.

> **Связанные документы.** Модель статусов заказа — [`docs/order-lifecycle.md`](order-lifecycle.md)
> (три оси: обработка/оплата/выгрузка в 1С). Контракт обмена с 1С —
> [`docs/1c-api-spec.md`](1c-api-spec.md) и [`docs/1c-developer-task.md`](1c-developer-task.md).
> Реестр доменных событий — `apps/core/events.py` (см. раздел 5).

---

## 1. Принципы

1. **Каждый модуль — отдельное Django-приложение** с явной границей. Магазинные модули реализуются полностью, CRM/AI — каркасом (модели + контракт), включаются позже.
2. **Граница важнее реализации.** Можно переписать внутренности модуля — пока контракт не изменился, остальные модули не ломаются.
3. **Модули не лезут в чужие таблицы.** Никаких `OtherApp.models.X.objects.filter()` из чужого приложения. Только через сервисный слой или сигналы.
4. **Два способа связи:** синхронно — через **сервисный слой** (`services.py`), асинхронно/реактивно — через **сигналы** (события домена).
5. **Feature-флаги в `core`** включают/выключают модули. Это же — фундамент переиспользуемого движка: разным магазинам разный набор включённых модулей.
6. **AI спрятан за адаптером.** На старте AI живёт внутри Django (Celery-задачи + вызовы внешней модели). Вынос в отдельный сервис = смена внутренности `ai/services.py`, не контракта.
7. **Движок отделён от магазина.** Всё, что специфично для конкретного магазина (бренд, палитра, зоны доставки, реквизиты, тексты), живёт в конфигурации, а не в коде. Код — это переиспользуемый движок, «Профессионал» — его первый экземпляр. См. раздел 9.

---

## 2. Слои и зависимости

Зависимости направлены строго вниз. Модуль может звать слой ниже, но не выше.

```
┌─────────────────────────────────────────────────────────┐
│  Слой 4 — Интеграции (адаптеры внешних систем)           │
│  integration_1c · integration_max · integration_ship    │
├─────────────────────────────────────────────────────────┤
│  Слой 3 — AI (за адаптерным интерфейсом)                 │
│  ai_enrich · ai_recommend · ai_assist                    │
├─────────────────────────────────────────────────────────┤
│  Слой 2 — CRM (включается по мере)                       │
│  crm_clients · crm_sales · crm_tasks · analytics         │
├─────────────────────────────────────────────────────────┤
│  Слой 1 — Магазин (строим сразу)                         │
│  catalog · pricing · orders · payments · delivery ·      │
│  content · reviews                                       │
├─────────────────────────────────────────────────────────┤
│  Слой 0 — Ядро                                           │
│  core · accounts · notifications                         │
└─────────────────────────────────────────────────────────┘
```

**Правило зависимостей:**
- Ядро не зависит ни от кого.
- Магазин зависит только от ядра.
- CRM зависит от магазина и ядра, но **магазин не знает о CRM** (общается через сигналы).
- AI зависит от магазина/CRM через сервисный слой, но они не знают об AI.
- Интеграции — самый верхний слой: знают обо всех, но о них не знает никто (вызываются по сигналам и из Celery).

> Это и есть гибкость: магазин можно запустить без CRM и AI, потому что нижние слои не ссылаются на верхние.

---

## 3. Структура проекта (папки)

```
proff58/
├── manage.py
├── config/                      # настройки проекта (не приложение)
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── celery.py
│   └── urls.py
│
├── apps/
│   ├── core/                    # СЛОЙ 0
│   │   ├── events.py            # ЕДИНЫЙ реестр доменных сигналов (см. раздел 5)
│   │   ├── features.py          # feature-флаги
│   │   ├── services.py          # общие сервисы (напр. is_enabled())
│   │   └── models.py            # SiteSettings, общие абстракции (TimeStamped и т.п.)
│   ├── accounts/
│   │   ├── models.py            # User, Organization, OrganizationMember
│   │   ├── services.py          # регистрация, верификация B2B
│   │   └── receivers.py         # подписчики чужих событий (если нужны)
│   ├── notifications/
│   │   ├── services.py          # send(user, event, payload) — единая точка
│   │   ├── channels/            # max.py, email.py — реализации каналов
│   │   └── receivers.py         # слушает order_paid/order_status_changed и т.п.
│   │
│   ├── catalog/                 # СЛОЙ 1 — МАГАЗИН
│   │   ├── models.py            # Category, Product, Attribute, CategoryAttribute,
│   │   │                        #   AttributeOption, ProductAttributeValue
│   │   ├── services.py          # get_product, search, build_facets
│   │   ├── signals.py           # технические сигналы (attrs_cache)
│   │   └── api/                 # DRF: serializers, views, urls
│   ├── pricing/
│   │   ├── models.py            # PriceList, PriceGroup, ContractPrice, Promotion, Coupon
│   │   ├── services.py          # price_for(product, user) — главный контракт
│   │   └── (эмит price_changed)
│   ├── orders/
│   │   ├── models.py            # Cart, Order, OrderItem (статусы — 3 оси, см. order-lifecycle.md)
│   │   ├── services.py          # create_order, change_status, reserve_stock
│   │   └── (эмит order_created, order_paid, order_status_changed)
│   ├── payments/
│   │   ├── models.py            # Payment, Invoice
│   │   ├── services.py          # create_payment, handle_webhook, refund
│   │   └── (эмит payment_succeeded, payment_failed)
│   ├── delivery/
│   │   ├── models.py            # DeliveryMethod, DeliveryZone, DeliveryRate
│   │   ├── services.py          # calculate(address, cart) — стоимость и срок
│   │   └── ...
│   ├── content/                 # SEO, баннеры, статьи, акции-контент
│   ├── reviews/                 # отзывы с модерацией
│   │
│   ├── crm_clients/             # СЛОЙ 2 — CRM (каркас на старте)
│   │   ├── models.py            # ClientProfile, Interaction
│   │   ├── services.py          # log_interaction, get_client_360
│   │   └── receivers.py         # слушает order_*/user_registered (под feature-флагом)
│   ├── crm_sales/
│   │   ├── models.py            # Deal, Pipeline, Stage
│   │   ├── services.py          # create_deal_from_order
│   │   └── receivers.py         # слушает order_created, order_paid
│   ├── crm_tasks/
│   │   ├── models.py            # Task, Ticket
│   │   └── receivers.py
│   ├── analytics/
│   │   ├── services.py          # отчёты, агрегаты (read-only)
│   │   └── api/
│   │
│   ├── ai/                      # СЛОЙ 3 — AI (единый адаптер)
│   │   ├── services.py          # recommend(), enrich(), assist() — КОНТРАКТ
│   │   ├── providers/           # claude.py, openai.py — заменяемые реализации
│   │   ├── tasks.py             # Celery: enrich_product, batch_enrich
│   │   └── receivers.py         # слушает product_created → ставит задачу обогащения
│   │
│   ├── integration_1c/          # СЛОЙ 4 — ИНТЕГРАЦИИ  (реализовано как apps/sync_1c)
│   │   ├── importers.py         # парсинг файлов 1С → staging (цены/остатки/номенклатура)
│   │   ├── orders_api.py        # ОТДАЁТ GET /orders/new, ПРИНИМАЕТ POST /orders/confirm (pull)
│   │   ├── mapping.py           # маппинг код 1С ↔ Product
│   │   ├── services.py          # sync_prices_stock; serialize_new_orders, apply_order_confirm
│   │   └── tasks.py             # Celery Beat (импорт цен/остатков)
│   │                            # ВАЖНО: сайт НЕ пушит заказы — 1С сама их забирает
│   ├── integration_max/
│   │   ├── client.py            # обёртка MAX Bot API
│   │   ├── webhook.py           # приём событий
│   │   ├── handlers/            # auth.py (OTP), orders.py (статусы)
│   │   └── services.py          # send_message, request_contact
│   └── integration_ship/
│       └── providers/           # cdek.py, boxberry.py, ...
│
└── docs/
    ├── ARCHITECTURE.md          # этот документ
    ├── order-lifecycle.md       # модель статусов заказа (3 оси)
    ├── 1c-api-spec.md           # контракт обмена с 1С
    └── adr/                     # Architecture Decision Records
```

> **Текущее состояние реализации.** Уже существуют: `apps/core` (реестр событий
> `events.py`, #70), `apps/accounts`, `apps/catalog`, `apps/sync_1c`. Приложение
> `apps/sync_1c` — это реализация целевого `integration_1c` (имя оставлено
> историческим; переименование — отдельный рефактор). Модули `orders`, `payments`,
> `pricing`, `notifications` и пр. — в разработке по roadmap.

---

## 4. Контракты — сервисный слой

Сервисный слой — это публичный API модуля для **синхронных** вызовов. Всё, что снаружи модуля,
ходит только через `services.py`. Прямой импорт чужих моделей запрещён.

### 4.1 `pricing.services`
```python
def price_for(product_id: int, user=None, qty: int = 1) -> PriceResult:
    """Главный контракт ценообразования.
    Возвращает финальную цену с учётом роли (розница/B2B), скидок и количества.
    Никто, кроме pricing, не считает цены."""

# PriceResult: { base, final, currency, discount, price_type: retail|wholesale|contract }
```

### 4.2 `orders.services`
```python
def create_order(*, cart, user=None, guest_phone=None,
                 delivery, payment_method) -> Order: ...
def change_status(*, order, axis, new_status, actor) -> Order:
    """Двигает статус по одной из 3 осей (fulfillment/payment/sync_1c), проверяет
    матрицу прав actor. Эмитит order_status_changed. См. docs/order-lifecycle.md."""
def reserve_stock(*, order, minutes: int) -> None: ...
```

### 4.3 `delivery.services`
```python
def calculate(*, address, cart) -> DeliveryQuote:
    """Стоимость и срок доставки по зонам Пензы/области. Не знает о ценах товаров."""
# DeliveryQuote: { cost, days, method, zone }
```

### 4.4 `notifications.services`
```python
def send(*, user=None, chat_id=None, event: str, payload: dict) -> None:
    """Единая точка отправки. Сама выбирает канал (MAX/email) по настройкам пользователя.
    Остальные модули НЕ зовут MAX или email напрямую — только эту функцию."""
```

### 4.5 `ai.services` — адаптерный контракт (ключевой для будущего)
```python
def recommend(*, query: str, context: dict, limit: int = 5) -> list[Recommendation]:
    """Подбор товаров для покупателя. Внутри сегодня — вызов внешней модели + поиск по EAV.
    Завтра — может стать вызовом отдельного сервиса. Контракт не меняется."""

def enrich(*, product_id: int) -> EnrichResult:
    """Обогащение карточки: разбор названия, характеристики, описание. Вызывается из Celery."""

def assist(*, message: str, session: dict) -> AssistReply:
    """AI-консультант (бот MAX, V2). На старте — заглушка, контракт уже зафиксирован."""
```

### 4.6 `integration_1c.services` (реализовано в `apps/sync_1c`)
```python
def sync_prices_stock() -> SyncReport:
    """Импорт цен/остатков/номенклатуры. 1С САМА шлёт их в наш API (push из 1С),
    мы пишем ТОЛЬКО эти поля — контент сайта защищён."""

# Заказы — PULL-модель: сайт НИЧЕГО не выгружает в 1С. 1С сама забирает и подтверждает:
#   GET  /api/1c/orders/new     — 1С забирает новые заказы (sync_1c_status: pending → exported)
#   POST /api/1c/orders/confirm — 1С подтверждает резерв и двигает fulfillment_status
# Нет push_order и нет реакции на order_paid выгрузкой.
# Контракт: docs/1c-api-spec.md · модель статусов: docs/order-lifecycle.md
```

### 4.7 `catalog` — характеристики: EAV-истина и read-model (ADR, #96)

Правило провенанса и кэша характеристик товара:

* **Источник истины — `ProductAttributeValue`** (EAV-строка) + поля `source`/`confidence`.
  Приоритет перезаписи задаёт карта **`source_priority`** в `data/attribute_rules.json`:
  `manual > import_1c > regex > keyword > llm`. Авто-источник НЕ затирает значение более
  авторитетного (ручное и 1С неприкосновенны). `confidence` — только аналитика/AI, в
  решении о перезаписи НЕ участвует. `source` — choices `Source` в `models.py`.
* **`Product.attrs_cache` — read-model**, производная от EAV для фасетов/фильтров (#25).
  Его **не редактируют руками**: он всегда пересобирается (`services.rebuild_attrs_cache`
  или инлайн-bulk в `enrich_*`). Это держит кэш под контролем при росте до 40–60 ключей.
* Извлечение из названия — словарь `data/attribute_rules.json` + движок
  `apps/catalog/attribute_extract.py` (зеркало `tool_type.py`). Числовые характеристики
  (DECIMAL/INTEGER) поддерживают range-фильтры (`?<slug>_min/_max`, фильтр по
  `value_decimal`); вид фильтра выводится из типа атрибута, UI-ползунки — позже.

---

## 5. Контракты — сигналы (события домена)

Сигналы — для **асинхронной/реактивной** связи. Модуль-издатель не знает, кто слушает.
Это развязывает магазин и CRM/AI: магазин просто сообщает «заказ оплачен», а кто на это реагирует — его не касается.

**Реестр сигналов — единый, в `apps/core/events.py`.** Payload — стабильные
идентификаторы/снапшоты (не живые ORM-инстансы): подписчик перечитывает актуальное
состояние из БД (надёжно под Celery/несколькими воркерами).

| Сигнал | Издатель | Когда | Полезная нагрузка | Кто слушает |
|---|---|---|---|---|
| `user_registered` | accounts | новый пользователь | user_id | crm_clients, notifications |
| `b2b_verified` | accounts | юрлицо одобрено | user_id, organization_id | notifications, crm_sales |
| `product_created` | catalog | создан товар | product_id, source | ai (обогащение), analytics |
| `product_updated` | catalog | изменён товар | product_id, source, changed_fields | analytics, ai, поиск/индекс |
| `order_created` | orders | оформлен заказ | order_id | crm_sales, notifications |
| `order_paid` | orders | оплачен | order_id, payment_id | notifications, crm_sales |
| `order_status_changed` | orders | смена статуса | order_id, old_status, new_status | notifications, crm_tasks, analytics |
| `payment_succeeded` | payments | оплата прошла | payment_id, order_id | orders |
| `payment_failed` | payments | оплата не прошла | payment_id, order_id, reason | notifications |
| `price_changed` | pricing | изменилась цена | product_id, old_price, new_price | analytics, subscriptions(V2) |

> **Заказы и 1С.** В pull-модели `integration_1c` НЕ подписан на `order_created`/
> `order_paid` — 1С сама забирает новые заказы через `GET /api/1c/orders/new`.
> Поэтому в колонке «кто слушает» для заказов нет интеграции с 1С.

**Правило именования:** сигнал — это факт в прошедшем времени (`order_paid`, не `pay_order`). Издатель эмитит факт, не команду.

**Где объявляются и как эмитятся:**
- Все доменные сигналы — **только в `apps/core/events.py`**. Новый сигнал заводится там
  и только вместе с ADR (`docs/adr/`).
- Эмит — из **сервисного слоя (use-case) или admin-flow**, НЕ через `model.post_save`
  (иначе дубли и потеря контекста `source`/`changed_fields`).
- Эмит — через `transaction.on_commit(...)`, чтобы подписчик видел закоммиченные данные.
- Допустимые значения `source` — в `core.events.EventSource` (`admin`/`1c`/`system`/`api`).
- Слушатели подписываются в `receivers.py` своего модуля и регистрируются в `apps.py`
  (`ready()`), для опциональных модулей — под feature-флагом.

---

## 6. Как это даёт гибкость — три сценария

**Сценарий А — запуск без CRM.** `crm_*` модули выключены feature-флагом. Их `receivers.py` не подписаны. Магазин эмитит `order_paid` — слушает только `notifications`. Всё работает. Включаем CRM позже — подписываем ресиверы, история начинает копиться.

**Сценарий Б — AI из монолита в сервис.** Сегодня `ai.services.recommend()` внутри дёргает внешнюю модель. Нагрузка выросла → выносим в отдельный сервис. Меняем тело `recommend()` на HTTP-вызов к новому сервису. `catalog`, `orders` и фронтенд ничего не замечают — контракт тот же.

**Сценарий В — коробочная версия.** Каждому клиенту — свой набор feature-флагов: одному магазин без B2B, другому магазин + CRM, третьему всё включено. Код один, конфигурация разная. Это работает только потому, что модули развязаны с самого начала.

---

## 7. Правила для разработчиков (чек-лист на каждый PR)

- Не импортирую модели чужого приложения. Беру данные через его `services.py`.
- Новое межмодульное взаимодействие — это либо метод в `services.py`, либо сигнал. Документирую в этом файле.
- Реакция на событие другого модуля — через `receivers.py`, не прямым вызовом.
- Цену считает только `pricing`. Уведомление шлёт только `notifications`. Внешние системы трогает только слой интеграций.
- Новый доменный сигнал объявляю **только в `apps/core/events.py`** и только с ADR.
- Эмит сигнала — из use-case/admin, не из `model.post_save`; через `transaction.on_commit`.
- Новый модуль регистрирую в `core.features` с флагом (по умолчанию выключен, если это CRM/AI).
- Изменение контракта (сигнатуры сервиса или payload сигнала) — отдельный ADR в `docs/adr/`.

---

## 8. Что реализуем сейчас, а что каркасом

| Модуль | Статус на запуске «Профессионала» |
|---|---|
| core, accounts, notifications | Полная реализация |
| catalog, pricing, orders, payments, delivery, content, reviews | Полная реализация |
| integration_1c, integration_max, integration_ship | Полная реализация |
| ai_enrich (через `ai.services.enrich`) | Полная реализация (нужен для наполнения) |
| ai_recommend (`ai.services.recommend`) | Каркас + базовая версия (подбор по EAV) |
| ai_assist (`ai.services.assist`) | Каркас (контракт + заглушка), реализация в V2 |
| crm_clients, crm_sales, crm_tasks, analytics | Каркас: модели + receivers, выключены флагом |

> Каркас = приложение существует, модели и контракты объявлены, receivers написаны но не подписаны. Стоит дёшево сейчас, превращает будущее «переделать» в «дописать».

---

## 9. Движок и экземпляр магазина (CMS-готовность)

Цель — сделать «Профессионал» так, чтобы следующий магазин собирался из того же кода быстрее. Это **движок для своих проектов**, а не продукт на продажу: нет мультиарендности, маркетплейса модулей и биллинга. Один магазин — одна установка движка со своей конфигурацией.

**Главный принцип: извлекаем CMS из работающего магазина, а не строим в вакууме.** Сначала запускаем «Профессионал». На нём видно, что оказалось общим (движок), а что специфичным (настройки экземпляра). После запуска аккуратно достаём общее в переиспользуемое ядро — и второй магазин собирается из него за недели.

### 9.1 Что относится к движку, а что — к экземпляру

| Движок (переиспользуемый код) | Экземпляр магазина (конфигурация/данные) |
|---|---|
| Модули `apps/*`, их модели и контракты | Бренд: название, логотип, палитра, шрифты |
| Сервисный слой и сигналы | Контакты, реквизиты для счетов |
| Логика каталога (EAV), заказов, цен | Дерево категорий и наполнение конкретного магазина |
| Шаблоны и компоненты (структура) | Зоны и тарифы доставки (для «Профессионала» — Пенза) |
| Набор доступных модулей | Какие модули включены (feature-флаги) |
| Интеграции (1С, MAX, доставка) — код | Ключи, токены, параметры подключения |

**Правило при разработке:** когда пишете что-то специфичное для «Профессионала» (зоны Пензы, реквизиты, бренд), спросите себя — «это про движок или про этот магазин?». Если про магазин — выносим в конфигурацию.

### 9.2 Конфигурация экземпляра — `SiteSettings`

Специфика магазина хранится в данных, а не в коде. Модель в `core`:
```python
class SiteSettings(models.Model):
    """Настройки конкретного экземпляра магазина. Singleton.
    Всё, что отличает один магазин от другого — здесь, не в коде."""
    name = models.CharField(max_length=200)        # «Профессионал»
    logo = models.ImageField(...)
    primary_color = models.CharField(default="#00A14B")
    accent_color = models.CharField(default="#B5E61D")
    contacts = models.JSONField(default=dict)       # телефоны, адрес, email
    requisites = models.JSONField(default=dict)     # реквизиты для счетов
    region = models.CharField(default="Пенза")
    # доступные модули — через core.features, не здесь
```

### 9.3 Тема оформления отделена от логики

Шаблоны и статика структурируются так, чтобы следующий магазин получил другой вид, не трогая Python-код. Django это поддерживает из коробки (порядок поиска шаблонов, namespaced static). Логика — в `apps/*`, оформление — в теме. Цвета и шрифты берутся из `SiteSettings`, не зашиты в CSS.

### 9.4 Что НЕ делаем сейчас (это путь «продукт на продажу»)

Сознательно НЕ закладываем на старте, чтобы не утонуть в универсальности:
- Мультиарендность (одна установка — много магазинов).
- Маркетплейс/магазин модулей, биллинг, тарифы.
- Механизм обновления движка у клиентов без поломки их данных.
- Визуальный конструктор страниц.

> Эти вещи появляются только если решим превратить движок в продукт на продажу. Тогда это отдельный проект со своей экономикой. Сейчас наша задача — чтобы код «Профессионала» переиспользовался, а не продавался.
