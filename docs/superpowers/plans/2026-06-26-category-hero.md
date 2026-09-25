# Hero-баннер категории — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить редактируемый на уровне категории hero-баннер на странице списка товаров (`/catalog/<category>`), как на макете `list_products_main`.

**Architecture:** 4 новых поля на модели `Category` → миграция → группа полей в админке → hero внедряется в ответ facets-эндпоинта во вью `CategoryFacetsView` (свежий объект `category` + `request` для абсолютного URL, минуя кэш фасетов) → фронт-адаптер маппит `hero` в `Listing.category` → новый презентационный компонент `CategoryHero` рендерится в `ListingShell` с градиентным fallback без фото.

**Tech Stack:** Django 5 + DRF (backend), Next.js 16 + React 19 + TypeScript + Tailwind (frontend), PostgreSQL + pytest (тесты backend), django-treebeard (`Category` = MP_Node).

## Global Constraints

- Общение с командой — только на русском (CLAUDE.md §0).
- Python-стиль: ruff + black, line-length 100. Миграции исключены из линта.
- Тесты backend требуют PostgreSQL (CLAUDE.md §8); запуск `pytest apps/catalog`.
- `Category` — treebeard `MP_Node`: создавать в тестах через `Category.add_root(...)`, НЕ `Category.objects.create(...)`.
- Frontend: «This is NOT the Next.js you know» (`frontend/AGENTS.md`) — перед написанием фронт-кода свериться с `frontend/node_modules/next/dist/docs/`, учесть deprecation-нотисы.
- Frontend тест-раннера НЕТ — фронт-задачи верифицируются визуально (dev-сервер + скриншот), не юнит-тестами.
- 1С контента не касается: hero — чисто контентные поля сайта (CLAUDE.md §1), `external_id_1c` не трогаем.
- Все hero-поля `blank=True` — обратная совместимость существующих категорий.
- Денежные/прочие контракты API не меняем — только добавляем ключ `hero` в блок `category`.

---

### Task 1: Поля hero на модели Category + миграция

**Files:**
- Modify: `apps/catalog/models.py:53-79` (класс `Category`, после поля `image`)
- Create: `apps/catalog/migrations/00XX_category_hero.py` (генерируется `makemigrations`)
- Create: `apps/catalog/tests/test_category_hero.py`

**Interfaces:**
- Produces: поля `Category.hero_image` (ImageField), `Category.hero_eyebrow` (str), `Category.hero_cta_label` (str), `Category.hero_cta_href` (str). Используются Task 2 (admin), Task 3 (view).

- [ ] **Step 1: Написать падающий тест**

Создать `apps/catalog/tests/test_category_hero.py`:

```python
import pytest

from apps.catalog.models import Category


@pytest.mark.django_db
def test_category_hero_fields_default_blank():
    cat = Category.add_root(name="Перфораторы", slug="perforatory")
    assert cat.hero_eyebrow == ""
    assert cat.hero_cta_label == ""
    assert cat.hero_cta_href == ""
    assert not cat.hero_image


@pytest.mark.django_db
def test_category_hero_fields_persist():
    cat = Category.add_root(
        name="Перфораторы",
        slug="perforatory",
        hero_eyebrow="Надёжность, результат",
        hero_cta_label="Подобрать модель",
        hero_cta_href="/catalog/perforatory?tool_type=sds",
    )
    cat.refresh_from_db()
    assert cat.hero_eyebrow == "Надёжность, результат"
    assert cat.hero_cta_label == "Подобрать модель"
    assert cat.hero_cta_href == "/catalog/perforatory?tool_type=sds"
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest apps/catalog/tests/test_category_hero.py -v`
Expected: FAIL (`TypeError`/`FieldError` — поля `hero_*` не существуют)

- [ ] **Step 3: Добавить поля в модель**

В `apps/catalog/models.py`, в классе `Category` сразу после строки
`image = models.ImageField(_("Изображение"), upload_to="categories/", blank=True)`:

```python
    hero_image = models.ImageField(
        _("Hero: фон"), upload_to="categories/hero/", blank=True
    )
    hero_eyebrow = models.CharField(_("Hero: слоган"), max_length=120, blank=True)
    hero_cta_label = models.CharField(_("Hero: текст кнопки"), max_length=60, blank=True)
    hero_cta_href = models.CharField(_("Hero: ссылка кнопки"), max_length=512, blank=True)
```

- [ ] **Step 4: Сгенерировать миграцию**

Run: `python manage.py makemigrations catalog`
Expected: создан файл миграции с добавлением 4 полей.

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `pytest apps/catalog/tests/test_category_hero.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Прогнать ruff+black и закоммитить**

```bash
ruff check apps/catalog/models.py apps/catalog/tests/test_category_hero.py --fix
black apps/catalog/models.py apps/catalog/tests/test_category_hero.py
git add apps/catalog/models.py apps/catalog/migrations apps/catalog/tests/test_category_hero.py
git commit -m "feat(catalog): поля hero-баннера на модели Category + миграция"
```

---

### Task 2: Группа полей hero в админке категории

**Files:**
- Modify: `apps/catalog/admin.py` (класс `CategoryAdmin`)

**Interfaces:**
- Consumes: поля `Category.hero_*` из Task 1.

- [ ] **Step 1: Найти CategoryAdmin**

Run: `grep -n "class CategoryAdmin\|fieldsets\|fields\b\|class Category" apps/catalog/admin.py`
Прочитать текущую конфигурацию формы категории (есть ли `fieldsets` или `fields`).

- [ ] **Step 2: Добавить группу «Hero-баннер»**

Если у `CategoryAdmin` уже есть `fieldsets` — добавить новый кортеж-секцию. Если используются `fields`/нет явной группировки — ввести `fieldsets`, перечислив существующие поля в первой секции «Основное», и добавить секцию hero. Пример секции (вставить в `fieldsets`):

```python
        (
            "Hero-баннер",
            {
                "classes": ("collapse",),
                "fields": ("hero_image", "hero_eyebrow", "hero_cta_label", "hero_cta_href"),
            },
        ),
```

- [ ] **Step 3: Проверить, что админка грузится без ошибок**

Run: `python manage.py check`
Expected: `System check identified no issues`.

Если запущен dev-сервер — открыть `/admin/catalog/category/<id>/change/` и убедиться, что секция «Hero-баннер» (collapse) видна с 4 полями.

- [ ] **Step 4: ruff+black и коммит**

```bash
ruff check apps/catalog/admin.py --fix
black apps/catalog/admin.py
git add apps/catalog/admin.py
git commit -m "feat(catalog): группа полей hero-баннера в админке категории"
```

---

### Task 3: facets-эндпоинт отдаёт блок hero

**Files:**
- Modify: `apps/catalog/api/views.py` (`CategoryFacetsView.get`, ~строки 295-327)
- Modify: `apps/catalog/tests/test_category_hero.py` (добавить тесты эндпоинта)

**Interfaces:**
- Consumes: `Category.hero_*` (Task 1).
- Produces: в JSON-ответе `GET /api/catalog/categories/<slug>/facets/` блок
  `category.hero = {image: str|null, eyebrow: str, ctaLabel: str, ctaHref: str}`.
  Потребляется фронт-адаптером (Task 4).

- [ ] **Step 1: Написать падающие тесты эндпоинта**

Дописать в `apps/catalog/tests/test_category_hero.py`:

```python
@pytest.mark.django_db
def test_facets_endpoint_returns_hero_block(client):
    cat = Category.add_root(
        name="Перфораторы",
        slug="perforatory",
        hero_eyebrow="Надёжность, результат",
        hero_cta_label="Подобрать модель",
        hero_cta_href="/catalog/perforatory?tool_type=sds",
    )
    resp = client.get(f"/api/catalog/categories/{cat.slug}/facets/")
    assert resp.status_code == 200
    hero = resp.json()["category"]["hero"]
    assert hero["eyebrow"] == "Надёжность, результат"
    assert hero["ctaLabel"] == "Подобрать модель"
    assert hero["ctaHref"] == "/catalog/perforatory?tool_type=sds"
    assert hero["image"] is None


@pytest.mark.django_db
def test_facets_endpoint_hero_empty_by_default(client):
    cat = Category.add_root(name="Дрели", slug="dreli")
    resp = client.get(f"/api/catalog/categories/{cat.slug}/facets/")
    assert resp.status_code == 200
    hero = resp.json()["category"]["hero"]
    assert hero == {"image": None, "eyebrow": "", "ctaLabel": "", "ctaHref": ""}
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `pytest apps/catalog/tests/test_category_hero.py -k hero -v`
Expected: FAIL (`KeyError: 'hero'`)

- [ ] **Step 3: Внедрить hero во вью**

В `apps/catalog/api/views.py`, в `CategoryFacetsView.get`, заменить финальный
`return Response(data)` на блок, добавляющий hero из свежего `category`:

```python
        hero_image = category.hero_image
        try:
            hero_url = request.build_absolute_uri(hero_image.url) if hero_image else None
        except ValueError:
            hero_url = None
        data["category"]["hero"] = {
            "image": hero_url,
            "eyebrow": category.hero_eyebrow,
            "ctaLabel": category.hero_cta_label,
            "ctaHref": category.hero_cta_href,
        }
        return Response(data)
```

(Ранние `return Response(..., status=400)` для невалидного `stock_status` и `FacetError`
не трогаем — у них нет блока `category`, hero там не нужен.)

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `pytest apps/catalog/tests/test_category_hero.py -v`
Expected: PASS (все тесты файла).

- [ ] **Step 5: ruff+black и коммит**

```bash
ruff check apps/catalog/api/views.py apps/catalog/tests/test_category_hero.py --fix
black apps/catalog/api/views.py apps/catalog/tests/test_category_hero.py
git add apps/catalog/api/views.py apps/catalog/tests/test_category_hero.py
git commit -m "feat(catalog): facets-эндпоинт отдаёт блок hero категории"
```

---

### Task 4: Фронт — тип и адаптер hero

**Files:**
- Modify: `frontend/lib/types.ts` (`Listing.category`, ~строки 98-104)
- Modify: `frontend/lib/adapters.ts` (`ApiCategoryBlock` ~71-76, `fetchListingFromApi` return ~432-441)

**Interfaces:**
- Consumes: блок `category.hero` из ответа API (Task 3).
- Produces: `Listing.category.hero?: { image: string | null; eyebrow: string; ctaLabel: string; ctaHref: string }`. Потребляется `CategoryHero` (Task 5) и `ListingShell` (Task 6).

- [ ] **Step 1: Расширить тип Listing.category**

В `frontend/lib/types.ts`, в `Listing.category`, после поля
`breadcrumb: { label: string; href: string }[];` добавить:

```ts
    hero?: {
      image: string | null;
      eyebrow: string;
      ctaLabel: string;
      ctaHref: string;
    };
```

- [ ] **Step 2: Расширить ApiCategoryBlock в адаптере**

В `frontend/lib/adapters.ts`, в типе `ApiCategoryBlock`, добавить поле:

```ts
  hero?: {
    image: string | null;
    eyebrow?: string;
    ctaLabel?: string;
    ctaHref?: string;
  };
```

- [ ] **Step 3: Замапить hero в Listing**

В `frontend/lib/adapters.ts`, в `fetchListingFromApi`, в возвращаемом объекте
`category: { title, intro, breadcrumb }` добавить поле `hero` после `breadcrumb`:

```ts
      hero: categoryBlock?.hero
        ? {
            image: categoryBlock.hero.image ?? null,
            eyebrow: categoryBlock.hero.eyebrow ?? "",
            ctaLabel: categoryBlock.hero.ctaLabel ?? "",
            ctaHref: categoryBlock.hero.ctaHref ?? "",
          }
        : undefined,
```

- [ ] **Step 4: Проверить типы**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок (или те же предупреждения, что и до правок).

- [ ] **Step 5: Коммит**

```bash
git add frontend/lib/types.ts frontend/lib/adapters.ts
git commit -m "feat(frontend): тип и адаптер hero в Listing.category"
```

---

### Task 5: Компонент CategoryHero

**Files:**
- Create: `frontend/components/listing/CategoryHero.tsx`

**Interfaces:**
- Consumes: тип hero из Task 4.
- Produces: `CategoryHero({ title: string; intro?: string; hero?: Hero })` — JSX-секция с одним `<h1>`. Используется `ListingShell` (Task 6).

- [ ] **Step 1: Свериться с локальными доками Next**

Прочитать актуальные нотисы (`frontend/AGENTS.md`): компонент презентационный, без
хуков и без `next/image` (фон — обычный `<img>`, декоративный). Убедиться, что
плейн-компонент без `"use client"` корректно рендерится внутри клиентского дерева
(`ListingShell` помечен `"use client"`).

- [ ] **Step 2: Создать компонент**

Создать `frontend/components/listing/CategoryHero.tsx`:

```tsx
// Hero-баннер категории (PLP). Презентационный: данные приходят из Listing.category.
// Фон-фото опционально — без него фирменный градиент на токенах темы. Единственный <h1>
// страницы (старый удалён из ListingShell). CTA рендерится только при наличии label+href.

type Hero = {
  image: string | null;
  eyebrow: string;
  ctaLabel: string;
  ctaHref: string;
};

export function CategoryHero({
  title,
  intro,
  hero,
}: {
  title: string;
  intro?: string;
  hero?: Hero;
}) {
  const hasCta = Boolean(hero?.ctaLabel && hero?.ctaHref);
  return (
    <section className="relative mb-6 overflow-hidden rounded-xl border border-line bg-canvas">
      {hero?.image ? (
        // Декоративный фон → пустой alt.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={hero.image}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div
          aria-hidden
          className="absolute inset-0 bg-[radial-gradient(120%_120%_at_15%_20%,color-mix(in_srgb,var(--accent)_18%,transparent),transparent_55%)]"
        />
      )}
      {/* Затемняющий оверлей для контраста текста (≥ WCAG AA на тёмной теме). */}
      <div className="absolute inset-0 bg-gradient-to-r from-canvas/95 via-canvas/80 to-canvas/40" />

      <div className="relative z-10 max-w-2xl px-6 py-12 md:px-10 md:py-16">
        {hero?.eyebrow && (
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-accent">
            {hero.eyebrow}
          </p>
        )}
        <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink md:text-4xl">
          {title}
        </h1>
        {intro && <p className="mt-3 text-sm text-ink-2 md:text-base">{intro}</p>}
        {hasCta && (
          <a
            href={hero!.ctaHref}
            className="mt-5 inline-flex items-center rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition hover:opacity-90 motion-reduce:transition-none"
          >
            {hero!.ctaLabel}
          </a>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Проверить типы и линт**

Run: `cd frontend && npx tsc --noEmit && npx eslint components/listing/CategoryHero.tsx`
Expected: без ошибок.

- [ ] **Step 4: Коммит**

```bash
git add frontend/components/listing/CategoryHero.tsx
git commit -m "feat(frontend): компонент CategoryHero с градиентным fallback"
```

---

### Task 6: Интеграция в ListingShell + фикстура

**Files:**
- Modify: `frontend/components/listing/ListingShell.tsx` (импорт ~16; блок заголовка 200-220)
- Modify: `frontend/fixtures/listing.perforatory.json` (блок `category`)

**Interfaces:**
- Consumes: `CategoryHero` (Task 5), `Listing.category.hero` (Task 4).

- [ ] **Step 1: Импортировать CategoryHero**

В `frontend/components/listing/ListingShell.tsx`, рядом с другими импортами
компонентов листинга (после строки импорта `ProductGridSkeleton`):

```ts
import { CategoryHero } from "@/components/listing/CategoryHero";
```

- [ ] **Step 2: Заменить блок заголовка на hero + одиночный промо**

В `ListingShell.tsx` заменить текущий блок (строки ~200-220):

```tsx
      <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_320px]">
        <div>
          <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink">
            {listing.category.title}
          </h1>
          {listing.category.intro && (
            <p className="mt-2 max-w-2xl text-sm text-ink-2">{listing.category.intro}</p>
          )}
        </div>
        {listing.promo && (
          <a
            href={listing.promo.href}
            className="flex flex-col justify-center rounded-lg border border-line bg-raised p-4 transition hover:border-accent"
          >
            <span className="text-xs text-ink-3">{listing.promo.title}</span>
            <span className="mt-1 font-display text-lg font-semibold text-accent">
              {listing.promo.subtitle}
            </span>
          </a>
        )}
      </div>
```

на (h1+intro переезжают в hero; промо остаётся, отдельной строкой под hero):

```tsx
      <CategoryHero
        title={listing.category.title}
        intro={listing.category.intro}
        hero={listing.category.hero}
      />

      {listing.promo && (
        <a
          href={listing.promo.href}
          className="mb-5 flex flex-col justify-center rounded-lg border border-line bg-raised p-4 transition hover:border-accent lg:max-w-md"
        >
          <span className="text-xs text-ink-3">{listing.promo.title}</span>
          <span className="mt-1 font-display text-lg font-semibold text-accent">
            {listing.promo.subtitle}
          </span>
        </a>
      )}
```

- [ ] **Step 3: Добавить hero в фикстуру**

В `frontend/fixtures/listing.perforatory.json`, в объект `category`, после массива
`breadcrumb` добавить поле `hero` (запятая после `breadcrumb`-массива):

```json
    "hero": {
      "image": null,
      "eyebrow": "Надёжность · Результат",
      "ctaLabel": "Подобрать модель",
      "ctaHref": "#"
    }
```

- [ ] **Step 4: Проверить типы**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 5: Коммит**

```bash
git add frontend/components/listing/ListingShell.tsx frontend/fixtures/listing.perforatory.json
git commit -m "feat(frontend): hero в ListingShell, h1 в hero, промо сохранён"
```

---

### Task 7: Визуальная верификация

**Files:** нет правок (проверка).

- [ ] **Step 1: Поднять dev-сервер фронта на фикстурах**

```bash
cd frontend && NEXT_PUBLIC_USE_FIXTURES=true npm run dev
```

Дождаться ответа `200` на `http://localhost:3000/catalog/perforatory`.

- [ ] **Step 2: Снять скриншот и проверить**

Сделать скриншот `http://localhost:3000/catalog/perforatory` (browse/headless).
Проверить визуально:
- hero-секция вверху: eyebrow «Надёжность · Результат», крупный `<h1>` ПЕРФОРАТОРЫ,
  интро, лаймовая кнопка «Подобрать модель»;
- фон hero — градиент (т.к. `image: null`);
- промо-блок «Акция месяца» остался под hero;
- в DOM ровно один `<h1>` (старый из ListingShell удалён);
- фильтры/сетка/сортировка не сломались.

- [ ] **Step 3: Проверить ветку прод-API (опционально, если доступен backend)**

При локальном Django с применённой миграцией: задать категории `hero_eyebrow`/
`hero_cta_label`/`hero_cta_href` (и при желании `hero_image`) в админке, открыть
её PLP без `NEXT_PUBLIC_USE_FIXTURES` (с `INTERNAL_API_BASE_URL`) — hero берёт
данные из БД, при заданном фото показывает его, иначе градиент.

---

## Self-Review

**Spec coverage:**
- Поля модели (hero_image/eyebrow/cta_label/cta_href) → Task 1. ✓
- Миграция → Task 1. ✓
- Админка (группа полей) → Task 2. ✓
- API отдаёт hero (абсолютный URL, null при пустом) → Task 3. ✓
- Фронт тип + адаптер → Task 4. ✓
- Компонент CategoryHero + градиентный fallback + один h1 + CTA только при label+href → Task 5. ✓
- Интеграция в ListingShell, h1 в hero, промо на месте → Task 6. ✓
- Фикстура с примером hero → Task 6. ✓
- Backend-тесты (миграция/сериализация/пустые поля) → Task 1, Task 3. ✓
- Frontend-верификация (нет тест-раннера → визуально) → Task 7. ✓
- Вне объёма (foreground-вырезки, карусель, hero_enabled, аналитика) — не включены. ✓

**Отличие от спеки (осознанное):** спека допускала сборку hero в сериализаторе/билдере
фасетов; план уточняет — hero собирается во вью `CategoryFacetsView` (свежий объект +
request, вне кэша фасетов), чтобы правки в админке отражались сразу и абсолютный URL
не кэшировался с хостом. Функционально эквивалентно, надёжнее.

**Placeholder scan:** заглушек нет — весь код приведён дословно. ✓

**Type consistency:** форма `hero { image, eyebrow, ctaLabel, ctaHref }` одинакова в API
(Task 3), типе `Listing.category.hero` (Task 4), `ApiCategoryBlock` (Task 4),
компоненте `CategoryHero` (Task 5) и фикстуре (Task 6). ✓
