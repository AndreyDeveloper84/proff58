# Hero-баннер категории — дизайн

**Дата:** 2026-06-26
**Ветка:** `design/catalog-category-hero`
**Статус:** утверждён, готов к плану реализации

## Контекст и цель

На странице списка товаров (`/catalog/<category>`) сейчас сразу идёт компактный
блок «заголовок + интро + промо», без hero-баннера. Макет `list_products_main`
(папка «ИИ Макеты») предполагает тёмный hero на всю ширину: фоновое фото линейки
инструмента, слоган сверху, крупный заголовок категории, описание и лаймовая
CTA-кнопка «Подобрать модель».

Цель — добавить редактируемый на уровне категории hero-баннер через все слои:
модель `Category` → миграция → админка → API каталога → фронт. Каждая категория
получает свой баннер; категории без загруженного фото показывают фирменный
градиентный hero.

## Решения (зафиксированы при брейншторме)

- **Источник данных:** поле баннера в БД на категорию (не CSS-only, не статичный
  ассет). Каждая категория — свой hero.
- **Поля hero:** минимум — фон + слоган + CTA. Заголовок и описание
  переиспользуем из существующих `Category.title` (через `name`/`title`) и
  `Category.description`.
- **Fallback без фото:** градиентный hero показывается **всегда** (единый вид на
  всех категориях); без `hero_image` — тёмный градиент на токенах темы.
- **CTA:** произвольный `href` из БД. Пустой `href` или пустой `label` → кнопка
  не рендерится.
- **`<h1>`:** переезжает из `ListingShell` в hero (один `<h1>` на страницу).
- **Промо-блок** «Скидка до 20%» остаётся на месте под hero, не трогаем.
- **Foreground-вырезки товаров** с макета — НЕ делаем (YAGNI: отдельные PNG-ассеты
  на категорию). Только фоновое изображение.

## 1. Модель данных — `apps/catalog/models.py`, класс `Category`

Добавить 4 поля (рядом с существующими `description`, `image`):

| Поле | Тип | Назначение |
|---|---|---|
| `hero_image` | `ImageField(upload_to="categories/hero/", blank=True)` | фоновое фото hero |
| `hero_eyebrow` | `CharField(max_length=120, blank=True)` | слоган над заголовком |
| `hero_cta_label` | `CharField(max_length=60, blank=True)` | текст CTA-кнопки |
| `hero_cta_href` | `CharField(max_length=512, blank=True)` | ссылка CTA-кнопки |

`hero_image` отдельное поле, НЕ переиспользуем существующее `Category.image`
(оно остаётся под возможную плитку-превью категории, чтобы не перегружать смысл).

Плюс миграция (`apps/catalog/migrations/`). Все поля `blank=True` — обратная
совместимость, существующие категории валидны без правок.

## 2. API + проводка во фронт

**Backend (`apps/catalog/api/serializers.py`, `views.py`):**
- В блок категории листингового ответа добавить вложенный объект `hero`:
  ```json
  "hero": {
    "image": "<абсолютный URL или null>",
    "eyebrow": "<str>",
    "ctaLabel": "<str>",
    "ctaHref": "<str>"
  }
  ```
- `image` — абсолютный URL через `request.build_absolute_uri`, как у фото товаров
  (`ProductImageSerializer`, serializers.py:34). `null`, если `hero_image` пуст.
- Точное место сборки блока `category` листингового ответа уточняется на этапе
  плана (текущий листинговый эндпоинт во `views.py`; сериализатор категории с
  `intro`/`breadcrumb` найти и расширить, либо собрать hero рядом).

**Frontend:**
- `lib/types.ts`: расширить `Listing.category` опциональным полем:
  ```ts
  hero?: {
    image: string | null;
    eyebrow: string;
    ctaLabel: string;
    ctaHref: string;
  };
  ```
- Адаптер (`lib/adapters.ts`) маппит ответ API → `Listing.category.hero`.
- Фикстура `fixtures/listing.perforatory.json` дополняется примером `hero`
  (включая путь к демо-изображению), чтобы баннер был виден локально.

## 3. Frontend-компонент `components/listing/CategoryHero.tsx`

Презентационный компонент. Пропсы: `title` (из `category.title`), `intro`
(из `category.intro`/description), `hero` (объект из типа выше, опционален).

**Структура (слои):**
1. Фон: если `hero.image` — `next/image` (cover); иначе фирменный градиент на
   токенах (`--canvas`/`--surface` + лаймовый радиальный акцент `--accent`).
2. Затемняющий оверлей (для контраста текста на фото).
3. Контент (слева, вертикальное центрирование):
   - `eyebrow` — мелкий, uppercase, `tracking-wide`, `text-accent` (если не пуст).
   - `<h1>` = `title` — крупный, `font-display`, uppercase (визуально как сейчас).
   - `intro` — описание под заголовком, ограниченная ширина (`max-w-2xl`).
   - CTA — лаймовая `<a>` (`bg-accent text-accent-ink`), только если есть и
     `ctaLabel`, и `ctaHref`.

**Поведение:**
- Градиентный fallback показывается всегда (hero рендерится на каждой категории).
- Адаптив: меньшая высота на мобиле, читаемый крупный текст; `motion-reduce`
  отключает любые transition/анимации.
- A11y: ровно один `<h1>` на странице (старый `<h1>` удаляется из `ListingShell`),
  CTA — семантическая ссылка, контраст текста на оверлее ≥ WCAG AA, фон
  декоративный (пустой `alt`).

**Интеграция в `ListingShell.tsx`:**
- `<CategoryHero>` рендерится над хлебными крошками/контентом (в начале страницы,
  на всю ширину контейнера).
- Из текущего блока `mb-5 grid ... lg:grid-cols-[1fr_320px]` убирается `<h1>` и
  `intro` (переехали в hero). **Промо-блок остаётся** на месте (под hero).

## 4. Админка — `apps/catalog/admin.py`

В форме `CategoryAdmin` — группа полей «Hero-баннер» (`fieldsets`, `classes:
("collapse",)`):
- `hero_image` (с превью текущего изображения, по аналогии с другими ImageField),
- `hero_eyebrow`,
- `hero_cta_label`,
- `hero_cta_href`.

## 5. Тестирование

**Backend (pytest, Postgres — см. CLAUDE.md §8):**
- Миграция применяется без ошибок.
- Листинговый сериализатор отдаёт блок `hero` с абсолютным URL при наличии
  `hero_image`.
- Пустые hero-поля → корректный ответ (`image: null`, пустые строки), без 500.

**Frontend:**
- `CategoryHero` рендерит `eyebrow` и CTA при заполненных полях и скрывает их при
  пустых.
- Без `hero.image` рендерится градиентный вариант (нет `<img>`).
- Конкретный тест-раннер фронта уточняется на этапе плана (следовать существующей
  настройке тестов `frontend/`).

## Вне объёма (YAGNI)

- Foreground-вырезки товаров на hero (отдельные PNG-ассеты).
- Несколько слайдов/карусель в hero.
- Тоггл `hero_enabled`, отдельные `hero_title`/`hero_subtitle` (отклонено в пользу
  переиспользования title/description).
- A/B-варианты hero, аналитика кликов CTA (можно добавить позже отдельной фичей).

## Затрагиваемые файлы (ориентир)

- `apps/catalog/models.py` (+ новая миграция)
- `apps/catalog/admin.py`
- `apps/catalog/api/serializers.py`, `apps/catalog/api/views.py`
- `frontend/lib/types.ts`, `frontend/lib/adapters.ts`
- `frontend/fixtures/listing.perforatory.json`
- `frontend/components/listing/CategoryHero.tsx` (новый)
- `frontend/components/listing/ListingShell.tsx`
- тесты: `apps/catalog/tests/` + фронт (по настройке)
