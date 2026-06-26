# Главная страница «Профессионал» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить демо-страницу `frontend/app/page.tsx` на полноценную анимированную главную из макета `main` (7 блоков + перебор шапки) и расширить домен заявок на тип «консультация» без товара.

**Architecture:** Backend — небольшое расширение `apps/leads` (новый `kind=consultation`, `product` nullable, валидация в сериализаторе). Frontend — SSR-страница (Server Component) компонует блоки; анимации (параллакс/reveal/hover/count-up) — client-островки на `framer-motion`; данные категорий/товаров из API каталога, тексты/ассеты — конфиг `lib/home-content.ts`; форма консультации шлёт в существующий BFF `/api/inquiry`.

**Tech Stack:** Django 5 + DRF (leads), Next.js 16 (App Router, React 19, Server Components), TypeScript, Tailwind v4, framer-motion (`motion`), lucide-react, pytest (backend).

**Связанная спека:** `docs/superpowers/specs/2026-06-26-homepage-main-design.md`.

## Global Constraints

- Общение и весь UI-текст — **на русском**; кодировка/кириллица корректные.
- Дизайн-токены уже в `frontend/app/globals.css` — **новые цвета не вводить**, только утилиты (`bg-canvas`, `bg-surface`, `bg-raised`, `border-line`, `text-ink`/`text-ink-2`/`text-ink-3`, `text-accent`/`bg-accent`/`text-accent-ink`, `text-brand`, `font-display`).
- **Границы модулей:** фронт ходит в Django только через BFF (`/api/...`) или server-side хелперы (`lib/catalog.ts` → `lib/adapters.ts`). Прямых browser→Django запросов нет.
- Backend: события издаются через `transaction.on_commit` (паттерн уже в `apps/leads/services.py`). Сбой уведомления не валит создание заявки.
- Анимации **обязаны** уважать `prefers-reduced-motion` (статичный фолбэк).
- Изображения — `next/image` (в проекте `images.unoptimized = true`, `remotePatterns` не нужны).
- **Во фронте нет юнит-раннера** (в `package.json` только `lint`). Верификация фронт-задач = `npx tsc --noEmit` (типы) + `npm run lint` + ручная браузерная проверка. Backend-задачи — TDD на pytest.
- Тесты backend требуют PostgreSQL (см. CLAUDE.md §8): `docker compose up -d db`, затем `pytest`.
- Conventional Commits; коммитим часто. Рабочая ветка сессии — `claude/pdp-polish-a` (в чужие ветки не пушить).
- PDP/PLP-заявки (`kind ∈ {price_request, restock_notify}`) **по-прежнему требуют товар** — не сломать существующий контракт.

---

## Task 1: Backend — `consultation` kind, nullable product, сервис

**Files:**
- Modify: `apps/leads/models.py`
- Create: `apps/leads/migrations/0002_consultation_kind_nullable_product.py`
- Modify: `apps/leads/services.py:12-32`
- Modify: `apps/leads/tests/test_models.py`
- Modify: `apps/leads/tests/test_services.py`

**Interfaces:**
- Consumes: `apps.core.events.product_inquiry_created` (существует), `ProductInquiry` (существует).
- Produces:
  - `InquiryKind.CONSULTATION = "consultation"` (значение enum).
  - `ProductInquiry.product` теперь `null=True, blank=True`.
  - `create_inquiry(*, kind, product=None, phone, name="", message="") -> ProductInquiry` (у `product` появляется дефолт `None`).

- [ ] **Step 1: Failing-тест на модель и сервис**

В `apps/leads/tests/test_models.py` добавить:

```python
import pytest

from apps.leads.models import InquiryKind, ProductInquiry


@pytest.mark.django_db
def test_consultation_inquiry_has_no_product():
    inquiry = ProductInquiry.objects.create(
        kind=InquiryKind.CONSULTATION, product=None, phone="+79990001122"
    )
    assert inquiry.pk is not None
    assert inquiry.product_id is None
    assert inquiry.kind == "consultation"
    assert str(inquiry)  # __str__ не падает на product=None
```

В `apps/leads/tests/test_services.py` добавить:

```python
import pytest

from apps.leads.models import InquiryKind
from apps.leads.services import create_inquiry


@pytest.mark.django_db
def test_create_inquiry_consultation_without_product():
    inquiry = create_inquiry(
        kind=InquiryKind.CONSULTATION, phone="+79990001122", name="Иван", message="нужна дрель"
    )
    assert inquiry.product_id is None
    assert inquiry.kind == "consultation"
    assert inquiry.name == "Иван"
```

- [ ] **Step 2: Прогнать — тесты падают**

Run: `pytest apps/leads/tests/test_models.py::test_consultation_inquiry_has_no_product apps/leads/tests/test_services.py::test_create_inquiry_consultation_without_product -v`
Expected: FAIL — `consultation` нет в `InquiryKind`; `product` not-null нарушает constraint; `create_inquiry` требует `product`.

- [ ] **Step 3: Расширить модель**

В `apps/leads/models.py` — добавить вид и сделать `product` опциональным:

```python
class InquiryKind(models.TextChoices):
    PRICE_REQUEST = "price_request", _("Запрос цены")
    RESTOCK_NOTIFY = "restock_notify", _("Уведомить о поступлении")
    CONSULTATION = "consultation", _("Консультация")
```

```python
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="inquiries",
        verbose_name=_("Товар"),
        null=True,
        blank=True,
    )
```

И `__str__` — без падения на пустом товаре:

```python
    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.phone} ({self.product_id or '—'})"
```

- [ ] **Step 4: Сгенерировать миграцию**

Run: `python manage.py makemigrations leads --name consultation_kind_nullable_product`
Expected: создан `apps/leads/migrations/0002_consultation_kind_nullable_product.py` (AlterField `product` → null/blank; AlterField `kind` choices). Проверить глазами, что меняются только эти поля.

- [ ] **Step 5: Дать `product` дефолт в сервисе**

В `apps/leads/services.py` сигнатуру:

```python
def create_inquiry(*, kind, product=None, phone, name="", message=""):
```

(тело без изменений — `product_id` в событии станет `None` для консультации, подписчик это уже переносит).

- [ ] **Step 6: Прогнать — тесты проходят**

Run: `pytest apps/leads/tests/test_models.py apps/leads/tests/test_services.py -v`
Expected: PASS (включая прежние тесты — старый контракт цел).

- [ ] **Step 7: Commit**

```bash
git add apps/leads/models.py apps/leads/migrations/0002_consultation_kind_nullable_product.py apps/leads/services.py apps/leads/tests/test_models.py apps/leads/tests/test_services.py
git commit -m "feat(leads): тип заявки «консультация» без привязки к товару"
```

---

## Task 2: Backend — валидация сериализатора (product обязателен, кроме consultation)

**Files:**
- Modify: `apps/leads/api/serializers.py`
- Modify: `apps/leads/tests/test_serializers.py`
- Modify: `apps/leads/tests/test_api.py`

**Interfaces:**
- Consumes: `create_inquiry(*, kind, product=None, ...)` (Task 1), `InquiryKind.CONSULTATION` (Task 1).
- Produces: `ProductInquirySerializer` принимает `kind=consultation` без `product`; для прочих видов `product` обязателен. Ответ POST — `{id, kind, status}` (как сейчас).

- [ ] **Step 1: Failing-тесты сериализатора**

В `apps/leads/tests/test_serializers.py` добавить:

```python
import pytest

from apps.leads.api.serializers import ProductInquirySerializer
from apps.leads.models import InquiryKind


@pytest.mark.django_db
def test_consultation_valid_without_product():
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.CONSULTATION, "phone": "89990001122", "name": "Иван"}
    )
    assert s.is_valid(), s.errors
    inquiry = s.save()
    assert inquiry.product_id is None
    assert inquiry.phone == "+79990001122"


@pytest.mark.django_db
def test_price_request_requires_product():
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.PRICE_REQUEST, "phone": "89990001122"}
    )
    assert not s.is_valid()
    assert "product" in s.errors
```

- [ ] **Step 2: Прогнать — падает**

Run: `pytest apps/leads/tests/test_serializers.py::test_consultation_valid_without_product apps/leads/tests/test_serializers.py::test_price_request_requires_product -v`
Expected: FAIL — сейчас `product` обязателен на уровне поля (consultation не пройдёт), а правило «обязателен для price_request» ещё не задано.

- [ ] **Step 3: Сделать product опциональным + кросс-валидация по kind**

В `apps/leads/api/serializers.py` заменить класс целиком на:

```python
class ProductInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductInquiry
        fields = ["id", "kind", "product", "phone", "name", "message", "status"]
        read_only_fields = ["id", "status"]
        extra_kwargs = {"product": {"required": False, "allow_null": True}}

    def validate_phone(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11 and digits[0] in {"7", "8"}:
            return "+7" + digits[1:]
        if len(digits) == 10:
            return "+7" + digits
        raise serializers.ValidationError("Укажите корректный номер телефона.")

    def validate(self, attrs):
        from apps.leads.models import InquiryKind

        if attrs.get("kind") != InquiryKind.CONSULTATION and not attrs.get("product"):
            raise serializers.ValidationError({"product": "Для этого типа заявки требуется товар."})
        return attrs

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "kind": instance.kind,
            "status": instance.status,
        }

    def create(self, validated_data):
        return create_inquiry(**validated_data)
```

(Импорты `re`, `serializers`, `ProductInquiry`, `create_inquiry` в файле уже есть — не дублировать.)

- [ ] **Step 4: Прогнать сериализатор — проходит**

Run: `pytest apps/leads/tests/test_serializers.py -v`
Expected: PASS.

- [ ] **Step 5: API-тест на приём консультации**

В `apps/leads/tests/test_api.py` добавить (использует существующий клиент/фикстуры файла — проверить имя URL/маршрута в начале файла и переиспользовать):

```python
@pytest.mark.django_db
def test_post_consultation_inquiry(api_client):
    resp = api_client.post(
        "/api/leads/inquiries/",
        {"kind": "consultation", "phone": "89990001122", "name": "Иван", "message": "подберите"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["kind"] == "consultation"
    assert set(body.keys()) == {"id", "kind", "status"}
```

Если в `test_api.py` нет фикстуры `api_client`, взять способ создания клиента из соседних тестов этого файла (повторить их паттерн) и URL заявок — из того же файла.

- [ ] **Step 6: Прогнать всё по leads**

Run: `pytest apps/leads -v`
Expected: PASS (старые тесты PDP-заявок целы).

- [ ] **Step 7: Commit**

```bash
git add apps/leads/api/serializers.py apps/leads/tests/test_serializers.py apps/leads/tests/test_api.py
git commit -m "feat(leads): сериализатор принимает консультацию без товара, товар обязателен для прочих видов"
```

---

## Task 3: Frontend — конфиг `lib/home-content.ts` + плейсхолдеры ассетов

**Files:**
- Create: `frontend/lib/home-content.ts`
- Create: `frontend/public/home/.gitkeep`, `frontend/public/home/hero/.gitkeep`, `frontend/public/home/categories/.gitkeep`
- Create: `frontend/public/home/categories/placeholder.svg`

**Interfaces:**
- Produces:
  - `type HomeStat = { value: number; suffix: string; label: string }`
  - `type NavLink = { label: string; href: string }`
  - `type TrustItem = { icon: string; title: string }`
  - `HOME_CONTENT` — объект с полями `topbar, nav, account, hero, categoryAssets, bestsellerSlugs, trust, consult, about`.
  - `categoryAsset(slug: string): string` — путь к ассету плитки (или дефолт-плейсхолдер).

- [ ] **Step 1: Создать конфиг**

`frontend/lib/home-content.ts`:

```ts
// Контент главной страницы, которого НЕТ в API каталога: тексты, статистика, телефон,
// промо, ссылки и визуальные ассеты категорий/hero. Перекраска/смена копий магазина —
// правка ТОЛЬКО этого файла, без касания компонентов. Названия категорий и сами товары
// приходят из API; здесь — лишь привязка slug→картинка и курируемый список «хитов».

export type HomeStat = { value: number; suffix: string; label: string };
export type NavLink = { label: string; href: string };
export type TrustItem = { icon: string; title: string };

export const HOME_CONTENT = {
  topbar: {
    promo: "Бесплатная доставка по Пензе от 5 000 ₽",
    phone: "8 (800) 600-44-99",
    phoneHref: "tel:+78006004499",
  },
  nav: [
    { label: "Акции", href: "#" },
    { label: "Доставка и оплата", href: "#" },
    { label: "Гарантия", href: "#" },
    { label: "Сервис", href: "#" },
    { label: "Компания", href: "#" },
    { label: "Контакты", href: "#" },
  ] as NavLink[],
  account: [
    { label: "Личный кабинет", href: "#" },
    { label: "Избранное", href: "#" },
    { label: "Сравнение", href: "#" },
  ] as NavLink[],
  hero: {
    titleLine1: "ПРОФЕССИОНАЛЬНЫЙ ИНСТРУМЕНТ",
    titleLine2: "для тех, кто создаёт будущее",
    bullets: [
      "Официальная гарантия",
      "Профессиональная консультация",
      "Доставка по Пензе и области",
    ],
    primaryCta: { label: "Перейти в магазин", href: "/catalog" },
  },
  // slug корневой категории → фон плитки (плейсхолдеры; дизайнер заменит). Дефолт — ниже.
  categoryAssets: {} as Record<string, string>,
  // Курируемые «хиты»: slug'и товаров. Пусто → fallback на ?sort=new (см. lib/catalog.ts).
  bestsellerSlugs: [] as string[],
  trust: [
    { icon: "ShieldCheck", title: "Официальная гарантия" },
    { icon: "Truck", title: "Быстрая доставка" },
    { icon: "Store", title: "Самовывоз" },
    { icon: "Wrench", title: "Сервис и запчасти" },
    { icon: "Building2", title: "Работаем с юрлицами" },
  ] as TrustItem[],
  consult: {
    title: "Не знаете, какой инструмент выбрать?",
    text: "Поможем подобрать инструмент под вашу задачу, бюджет и условия работы.",
    maxUrl: "https://max.ru/proffinstrument",
  },
  about: {
    title: "О магазине «Профессионал»",
    text: "Магазин профессионального электро- и ручного инструмента с доставкой по Пензе и области.",
    stats: [
      { value: 10, suffix: "+", label: "лет на рынке" },
      { value: 20000, suffix: "+", label: "товаров в каталоге" },
      { value: 50000, suffix: "+", label: "довольных клиентов" },
      { value: 100, suffix: "+", label: "брендов" },
    ] as HomeStat[],
  },
};

// Фон плитки категории. Нет ассета для slug → нейтральный плейсхолдер.
export function categoryAsset(slug: string): string {
  return HOME_CONTENT.categoryAssets[slug] ?? "/home/categories/placeholder.svg";
}
```

- [ ] **Step 2: Создать каталоги ассетов и плейсхолдер**

```bash
mkdir -p frontend/public/home/hero frontend/public/home/categories
touch frontend/public/home/.gitkeep frontend/public/home/hero/.gitkeep frontend/public/home/categories/.gitkeep
```

Создать `frontend/public/home/categories/placeholder.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" viewBox="0 0 320 240"><rect width="320" height="240" fill="#1e2226"/><rect x="0.5" y="0.5" width="319" height="239" fill="none" stroke="#2a2f34"/></svg>
```

- [ ] **Step 3: Типобезопасность**

Run (из `frontend/`): `npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/home-content.ts frontend/public/home
git commit -m "feat(home): конфиг контента главной и плейсхолдеры ассетов"
```

---

## Task 4: Frontend — хелперы данных `getCategoryTree()` и `getBestsellers()`

**Files:**
- Modify: `frontend/lib/adapters.ts` (добавить две fetch-функции в конец файла)
- Modify: `frontend/lib/catalog.ts` (дополнить импорт из `./adapters`, добавить два хелпера + реэкспорт типа)

**Interfaces:**
- Consumes: `apiProductToProduct(ap): Product` (существует в adapters.ts), тип `ApiProduct` (существует там же), `Product` (lib/types), `HOME_CONTENT.bestsellerSlugs` (Task 3), `INTERNAL_API_BASE_URL`.
- Produces:
  - `type CategoryNode = { id: number; name: string; slug: string; sort_order: number; children: CategoryNode[] }`
  - `getCategoryTree(): Promise<CategoryNode[]>` — корневые категории (пустой массив при сбое/без API).
  - `getBestsellers(limit?: number): Promise<Product[]>` — курируемые slug'и или `?sort=new` fallback (пустой массив при сбое).

- [ ] **Step 1: Адаптеры в `lib/adapters.ts`**

Добавить в конец `frontend/lib/adapters.ts` (`SSR_HEADERS`, `apiProductToProduct`, тип `ApiProduct`, тип `Product` уже доступны в файле):

```ts
// --- Главная страница ---

export type CategoryNode = {
  id: number;
  name: string;
  slug: string;
  sort_order: number;
  children: CategoryNode[];
};

// Дерево категорий для блока «Категории» главной. Best-effort: сбой/невалид → пустой массив
// (главная деградирует мягко, в отличие от PLP). Возвращаем как есть — корни возьмёт хелпер.
export async function fetchCategoryTreeFromApi(base: string): Promise<CategoryNode[]> {
  const root = base.replace(/\/$/, "");
  try {
    const res = await fetch(`${root}/api/catalog/categories/`, {
      cache: "no-store",
      headers: SSR_HEADERS,
    });
    if (!res.ok) return [];
    const json = (await res.json()) as CategoryNode[];
    return Array.isArray(json) ? json : [];
  } catch {
    return [];
  }
}

// «Хиты продаж»: курируемые slug'и (detail-эндпоинт, параллельно) → fallback ?sort=new.
// Detail-ответ — надмножество list (ApiProduct), apiProductToProduct берёт нужное подмножество.
export async function fetchBestsellersFromApi(
  base: string,
  slugs: string[],
  limit: number,
): Promise<Product[]> {
  const root = base.replace(/\/$/, "");
  if (slugs.length) {
    const settled = await Promise.all(
      slugs.map(async (slug) => {
        try {
          const res = await fetch(`${root}/api/catalog/products/${encodeURIComponent(slug)}/`, {
            cache: "no-store",
            headers: SSR_HEADERS,
          });
          if (!res.ok) return null;
          return apiProductToProduct((await res.json()) as ApiProduct);
        } catch {
          return null;
        }
      }),
    );
    const found = settled.filter((p): p is Product => p != null);
    if (found.length) return found;
  }
  // Fallback: свежие товары.
  try {
    const res = await fetch(`${root}/api/catalog/products/?sort=new&limit=${limit}`, {
      cache: "no-store",
      headers: SSR_HEADERS,
    });
    if (!res.ok) return [];
    const json = (await res.json()) as { results?: ApiProduct[] };
    return (json.results ?? []).map(apiProductToProduct);
  } catch {
    return [];
  }
}
```

- [ ] **Step 2: Хелперы в `lib/catalog.ts`**

В `frontend/lib/catalog.ts` дополнить существующий импорт из `./adapters` новыми именами и добавить импорт конфига:

```ts
import {
  fetchListingFromApi,
  fetchProductFromApi,
  fetchSearchFromApi,
  fetchCategoryTreeFromApi,
  fetchBestsellersFromApi,
  type CategoryNode,
} from "./adapters";
import { HOME_CONTENT } from "./home-content";
```

(Старую строку импорта из `./adapters` заменить на эту — не плодить второй импорт. `applyListing`, `import perforatory ...` и прочее не трогать.)

В конец файла:

```ts
export type { CategoryNode };

// Корневые категории (depth==1) для блока главной. Без API → пусто (блок скрыт).
export async function getCategoryTree(): Promise<CategoryNode[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchCategoryTreeFromApi(API_BASE);
  }
  return [];
}

// «Хиты продаж» для главной. Без API → пусто (блок скрыт).
export async function getBestsellers(limit = 8): Promise<Product[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchBestsellersFromApi(API_BASE, HOME_CONTENT.bestsellerSlugs, limit);
  }
  return [];
}
```

(`API_BASE`, `FORCE_FIXTURES`, тип `Product` уже доступны в `lib/catalog.ts`.)

- [ ] **Step 3: Типобезопасность**

Run (из `frontend/`): `npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/adapters.ts frontend/lib/catalog.ts
git commit -m "feat(home): server-хелперы дерева категорий и хитов продаж"
```

---

## Task 5: Frontend — зависимость `motion` + обёртки `Reveal` и `Parallax`

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (через npm install)
- Create: `frontend/components/motion/Reveal.tsx`
- Create: `frontend/components/motion/Parallax.tsx`

**Interfaces:**
- Produces:
  - `<Reveal className?, delay?, children>` — fade-up при входе во вьюпорт (once); при reduced-motion — статично.
  - `<Parallax speed?, className?, children>` — сдвиг по Y от скролла; при reduced-motion — без сдвига.

- [ ] **Step 1: Установить motion**

Run (из `frontend/`): `npm install motion`
Expected: `motion` в `dependencies`, `package-lock.json` обновлён.

- [ ] **Step 2: `Reveal.tsx`**

`frontend/components/motion/Reveal.tsx`:

```tsx
"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

type RevealProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
};

// Появление снизу-вверх при первом входе во вьюпорт. reduced-motion → без анимации.
export function Reveal({ children, className, delay = 0 }: RevealProps) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
```

- [ ] **Step 3: `Parallax.tsx`**

`frontend/components/motion/Parallax.tsx`:

```tsx
"use client";

import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useRef, type ReactNode } from "react";

type ParallaxProps = {
  children: ReactNode;
  className?: string;
  // px смещения на проход секции через вьюпорт. >0 — медленнее (вниз), <0 — быстрее (вверх).
  speed?: number;
};

// Сдвиг слоя по Y в зависимости от прокрутки секции. reduced-motion → статично.
export function Parallax({ children, className, speed = 60 }: ParallaxProps) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [speed, -speed]);
  if (reduce) {
    return (
      <div ref={ref} className={className}>
        {children}
      </div>
    );
  }
  return (
    <motion.div ref={ref} className={className} style={{ y }}>
      {children}
    </motion.div>
  );
}
```

- [ ] **Step 4: Типобезопасность**

Run (из `frontend/`): `npx tsc --noEmit`
Expected: без ошибок. Если импорт `motion/react` не резолвится — проверить, что установлен пакет `motion` (он экспортирует подпуть `motion/react`).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/components/motion
git commit -m "feat(home): зависимость motion и обёртки Reveal/Parallax (reduced-motion-aware)"
```

---

## Task 6: Frontend — перебор шапки `Header.tsx`

**Files:**
- Modify: `frontend/components/layout/Header.tsx`

**Interfaces:**
- Consumes: `HOME_CONTENT.topbar/nav/account` (Task 3), `useCart` (существует), `SearchBar` (существует).
- Produces: обновлённый общий `Header` (используется в `app/layout.tsx`).

- [ ] **Step 1: Переписать Header**

`frontend/components/layout/Header.tsx` (полная замена):

```tsx
"use client";

import Link from "next/link";
import { useState } from "react";
import { Heart, Menu, Scale, ShoppingCart, User } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { HOME_CONTENT } from "@/lib/home-content";
import { SearchBar } from "./SearchBar";

const ACCOUNT_ICONS: Record<string, LucideIcon> = {
  "Личный кабинет": User,
  Избранное: Heart,
  Сравнение: Scale,
};

export function Header() {
  const { count } = useCart();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/95 backdrop-blur">
      {/* Топ-бар: промо + телефон + аккаунт-ссылки (скрыт на мобиле) */}
      <div className="hidden border-b border-line/60 lg:block">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-1.5 text-xs text-ink-3 sm:px-6 lg:px-8">
          <span>{HOME_CONTENT.topbar.promo}</span>
          <div className="flex items-center gap-5">
            <a
              href={HOME_CONTENT.topbar.phoneHref}
              className="font-medium text-ink-2 hover:text-ink"
            >
              {HOME_CONTENT.topbar.phone}
            </a>
            {HOME_CONTENT.account.map((l) => (
              <Link key={l.label} href={l.href} className="transition hover:text-ink">
                {l.label}
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Основная строка: бургер + лого + поиск + иконки */}
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <button
          type="button"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-raised lg:hidden"
          aria-label="Меню"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>
        <Link
          href="/"
          className="shrink-0 font-display text-xl font-bold uppercase tracking-wide text-accent"
        >
          Профессионал
        </Link>
        <div className="flex-1">
          <SearchBar />
        </div>
        <Link
          href="/cart"
          className="relative grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 transition hover:bg-raised hover:text-ink"
          aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
        >
          <ShoppingCart className="h-5 w-5" aria-hidden />
          {count > 0 && (
            <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink">
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Link>
      </div>

      {/* Нав-меню (десктоп) */}
      <nav className="hidden border-t border-line/60 lg:block">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-2 text-sm sm:px-6 lg:px-8">
          {HOME_CONTENT.nav.map((l) => (
            <Link key={l.label} href={l.href} className="text-ink-2 transition hover:text-accent">
              {l.label}
            </Link>
          ))}
        </div>
      </nav>

      {/* Мобильное меню */}
      {open && (
        <div className="border-t border-line bg-surface lg:hidden">
          <nav className="mx-auto flex max-w-7xl flex-col px-4 py-2 sm:px-6">
            {[...HOME_CONTENT.nav, ...HOME_CONTENT.account].map((l) => {
              const Icon = ACCOUNT_ICONS[l.label];
              return (
                <Link
                  key={l.label}
                  href={l.href}
                  className="flex items-center gap-2 border-b border-line/40 py-2.5 text-sm text-ink-2 last:border-0 hover:text-accent"
                  onClick={() => setOpen(false)}
                >
                  {Icon && <Icon className="h-4 w-4" aria-hidden />}
                  {l.label}
                </Link>
              );
            })}
            <a
              href={HOME_CONTENT.topbar.phoneHref}
              className="py-2.5 text-sm font-medium text-ink"
            >
              {HOME_CONTENT.topbar.phone}
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок и без предупреждений о неиспользуемых импортах.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/layout/Header.tsx
git commit -m "feat(header): топ-бар, нав-меню, аккаунт-ссылки и мобильный бургер по макету"
```

---

## Task 7: Frontend — блок Hero (параллакс слоёв)

**Files:**
- Create: `frontend/components/home/Hero.tsx`

**Interfaces:**
- Consumes: `HOME_CONTENT.hero` (Task 3), `Parallax` (Task 5).
- Produces: `<Hero onConsult={() => void} />` — кнопка «Получить консультацию» вызывает `onConsult` (модалку открывает страница, Task 14).

- [ ] **Step 1: Создать Hero**

`frontend/components/home/Hero.tsx`:

```tsx
"use client";

import Link from "next/link";
import { ArrowRight, MessageSquareText } from "lucide-react";
import { Parallax } from "@/components/motion/Parallax";
import { HOME_CONTENT } from "@/lib/home-content";

type HeroProps = { onConsult: () => void };

export function Hero({ onConsult }: HeroProps) {
  const h = HOME_CONTENT.hero;
  return (
    <section className="relative overflow-hidden bg-canvas">
      {/* Слой 1 — дальний фон */}
      <Parallax speed={40} className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_30%,rgba(0,161,75,0.18),transparent_55%)]" />
      </Parallax>
      {/* Слой 2 — средний (декоративный градиент) */}
      <Parallax speed={-30} className="pointer-events-none absolute inset-0 -z-10 opacity-40">
        <div className="absolute right-0 top-0 h-full w-2/3 bg-[linear-gradient(115deg,transparent,rgba(181,230,29,0.08))]" />
      </Parallax>

      <div className="mx-auto grid max-w-7xl items-center gap-8 px-4 py-16 sm:px-6 md:grid-cols-2 md:py-24 lg:px-8">
        {/* Слой 5 — текст/CTA (всегда поверх, самый «быстрый») */}
        <div className="relative z-10 max-w-xl">
          <h1 className="font-display text-4xl font-bold uppercase leading-tight tracking-wide text-ink sm:text-5xl">
            {h.titleLine1}
          </h1>
          <p className="mt-2 font-display text-xl text-accent sm:text-2xl">{h.titleLine2}</p>
          <ul className="mt-6 space-y-2 text-sm text-ink-2">
            {h.bullets.map((b) => (
              <li key={b} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
                {b}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href={h.primaryCta.href}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-3 text-sm font-semibold text-accent-ink transition hover:brightness-110"
            >
              {h.primaryCta.label}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            <button
              type="button"
              onClick={onConsult}
              className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-5 py-3 text-sm font-semibold text-ink transition hover:bg-raised"
            >
              <MessageSquareText className="h-4 w-4" aria-hidden />
              Получить консультацию
            </button>
          </div>
        </div>

        {/* Слой 4 — объект (фото-инструмент); плейсхолдер до ассета дизайнера */}
        <Parallax speed={-50} className="relative z-0 hidden md:block">
          <div className="aspect-square w-full rounded-lg border border-line bg-[radial-gradient(circle_at_50%_40%,rgba(181,230,29,0.12),rgba(30,34,38,0.9))]" />
        </Parallax>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/Hero.tsx
git commit -m "feat(home): hero-блок с параллаксом слоёв и CTA"
```

---

## Task 8: Frontend — блок «Категории» (`CategoryGrid`)

**Files:**
- Create: `frontend/components/home/CategoryGrid.tsx`

**Interfaces:**
- Consumes: `CategoryNode` (Task 4, реэкспорт из `lib/catalog`), `categoryAsset(slug)` (Task 3), `Reveal` (Task 5).
- Produces: `<CategoryGrid categories={CategoryNode[]} />` (рендерит максимум 6 корней; пустой массив → `null`).

- [ ] **Step 1: Создать CategoryGrid**

`frontend/components/home/CategoryGrid.tsx`:

```tsx
"use client";

import Image from "next/image";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { Reveal } from "@/components/motion/Reveal";
import { categoryAsset } from "@/lib/home-content";
import type { CategoryNode } from "@/lib/catalog";

type CategoryGridProps = { categories: CategoryNode[] };

export function CategoryGrid({ categories }: CategoryGridProps) {
  const reduce = useReducedMotion();
  const items = categories.slice(0, 6);
  if (!items.length) return null;

  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {items.map((cat, i) => (
          <Reveal key={cat.id} delay={reduce ? 0 : i * 0.05}>
            <motion.div whileHover={reduce ? undefined : { y: -4 }} className="h-full">
              <Link
                href={`/catalog/${cat.slug}`}
                className="group flex h-full flex-col overflow-hidden rounded-lg border border-line bg-surface transition hover:border-accent"
              >
                <div className="relative aspect-[4/3] overflow-hidden bg-raised">
                  <Image
                    src={categoryAsset(cat.slug)}
                    alt={cat.name}
                    fill
                    sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 16vw"
                    className="object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                </div>
                <span className="px-3 py-3 text-sm font-medium text-ink-2 transition group-hover:text-ink">
                  {cat.name}
                </span>
              </Link>
            </motion.div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/CategoryGrid.tsx
git commit -m "feat(home): блок категорий с hover и stagger-reveal"
```

---

## Task 9: Frontend — блок «Доверие» (`TrustBadges`)

**Files:**
- Create: `frontend/components/home/TrustBadges.tsx`

**Interfaces:**
- Consumes: `HOME_CONTENT.trust` (Task 3), `Reveal` (Task 5), lucide-иконки по имени.
- Produces: `<TrustBadges />`.

- [ ] **Step 1: Создать TrustBadges**

`frontend/components/home/TrustBadges.tsx`:

```tsx
"use client";

import { Building2, ShieldCheck, Store, Truck, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Reveal } from "@/components/motion/Reveal";
import { HOME_CONTENT } from "@/lib/home-content";

const ICONS: Record<string, LucideIcon> = {
  ShieldCheck,
  Truck,
  Store,
  Wrench,
  Building2,
};

export function TrustBadges() {
  return (
    <section className="border-y border-line bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Reveal>
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {HOME_CONTENT.trust.map((item) => {
              const Icon = ICONS[item.icon] ?? ShieldCheck;
              return (
                <li key={item.title} className="flex items-center gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-raised text-brand">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className="text-sm text-ink-2">{item.title}</span>
                </li>
              );
            })}
          </ul>
        </Reveal>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/TrustBadges.tsx
git commit -m "feat(home): блок преимуществ с reveal-on-scroll"
```

---

## Task 10: Frontend — блок «Хиты продаж» (`Bestsellers`, карусель)

**Files:**
- Create: `frontend/components/home/Bestsellers.tsx`

**Interfaces:**
- Consumes: `Product` (lib/types), `ProductCard` (существует), `Reveal` (Task 5).
- Produces: `<Bestsellers products={Product[]} />` (пустой массив → `null`).

- [ ] **Step 1: Создать Bestsellers**

`frontend/components/home/Bestsellers.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useRef } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { ProductCard } from "@/components/product/ProductCard";
import { Reveal } from "@/components/motion/Reveal";
import type { Product } from "@/lib/types";

type BestsellersProps = { products: Product[] };

export function Bestsellers({ products }: BestsellersProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  if (!products.length) return null;

  const scrollBy = (dir: 1 | -1) => {
    trackRef.current?.scrollBy({ left: dir * 280, behavior: "smooth" });
  };

  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="mb-5 flex items-end justify-between gap-4">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-wide text-ink">
          Хиты продаж
        </h2>
        <div className="flex items-center gap-2">
          <Link href="/catalog" className="hidden text-sm text-ink-2 transition hover:text-accent sm:inline">
            Смотреть все
          </Link>
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:bg-raised hover:text-ink"
            aria-label="Прокрутить влево"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:bg-raised hover:text-ink"
            aria-label="Прокрутить вправо"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      <Reveal>
        <div
          ref={trackRef}
          className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {products.map((p) => (
            <div key={p.id} className="w-[240px] shrink-0 snap-start">
              <ProductCard product={p} />
            </div>
          ))}
        </div>
      </Reveal>

      <Link
        href="/catalog"
        className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-accent sm:hidden"
      >
        Смотреть все
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </section>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/Bestsellers.tsx
git commit -m "feat(home): карусель хитов продаж (scroll-snap + стрелки)"
```

---

## Task 11: Frontend — блок «Консультация» (`ConsultBlock`, параллакс-фон)

**Files:**
- Create: `frontend/components/home/ConsultBlock.tsx`

**Interfaces:**
- Consumes: `HOME_CONTENT.consult` (Task 3), `Parallax` (Task 5).
- Produces: `<ConsultBlock onConsult={() => void} />` — «Подобрать инструмент» вызывает `onConsult`; «Консультация в MAX» — внешняя ссылка.

- [ ] **Step 1: Создать ConsultBlock**

`frontend/components/home/ConsultBlock.tsx`:

```tsx
"use client";

import { MessageSquareText, Wrench } from "lucide-react";
import { Parallax } from "@/components/motion/Parallax";
import { HOME_CONTENT } from "@/lib/home-content";

type ConsultBlockProps = { onConsult: () => void };

export function ConsultBlock({ onConsult }: ConsultBlockProps) {
  const c = HOME_CONTENT.consult;
  return (
    <section className="relative overflow-hidden border-y border-line">
      {/* Параллакс-фон (плейсхолдер-градиент до фото дизайнера) */}
      <Parallax speed={50} className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(14,17,19,0.96),rgba(30,34,38,0.7))]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_85%_50%,rgba(0,161,75,0.22),transparent_55%)]" />
      </Parallax>

      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-wide text-ink sm:text-3xl">
            {c.title}
          </h2>
          <p className="mt-3 text-ink-2">{c.text}</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onConsult}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-3 text-sm font-semibold text-accent-ink transition hover:brightness-110"
            >
              <Wrench className="h-4 w-4" aria-hidden />
              Подобрать инструмент
            </button>
            <a
              href={c.maxUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-5 py-3 text-sm font-semibold text-ink transition hover:bg-raised"
            >
              <MessageSquareText className="h-4 w-4" aria-hidden />
              Консультация в MAX
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/ConsultBlock.tsx
git commit -m "feat(home): блок консультации с параллакс-фоном и CTA в MAX"
```

---

## Task 12: Frontend — блок «О магазине» (`AboutStats`, count-up)

**Files:**
- Create: `frontend/components/home/StatCounter.tsx`
- Create: `frontend/components/home/AboutStats.tsx`

**Interfaces:**
- Consumes: `HOME_CONTENT.about` (Task 3), `Reveal` (Task 5), `HomeStat` (Task 3).
- Produces: `<AboutStats />`; `<StatCounter value, suffix, label />` (count-up при появлении; reduced-motion → сразу финальное число).

- [ ] **Step 1: Создать StatCounter**

`frontend/components/home/StatCounter.tsx`:

```tsx
"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { HomeStat } from "@/lib/home-content";

export function StatCounter({ value, suffix, label }: HomeStat) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const [display, setDisplay] = useState(reduce ? value : 0);

  useEffect(() => {
    if (reduce || !inView) return;
    const controls = animate(0, value, {
      duration: 1.4,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, reduce, value]);

  return (
    <div ref={ref} className="text-center">
      <div className="font-display text-3xl font-bold text-accent sm:text-4xl">
        {display.toLocaleString("ru-RU")}
        {suffix}
      </div>
      <div className="mt-1 text-sm text-ink-3">{label}</div>
    </div>
  );
}
```

- [ ] **Step 2: Создать AboutStats**

`frontend/components/home/AboutStats.tsx`:

```tsx
"use client";

import { Reveal } from "@/components/motion/Reveal";
import { HOME_CONTENT } from "@/lib/home-content";
import { StatCounter } from "./StatCounter";

export function AboutStats() {
  const a = HOME_CONTENT.about;
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <Reveal>
        <h2 className="font-display text-2xl font-semibold uppercase tracking-wide text-ink sm:text-3xl">
          {a.title}
        </h2>
        <p className="mt-3 max-w-2xl text-ink-2">{a.text}</p>
      </Reveal>
      <div className="mt-10 grid grid-cols-2 gap-6 sm:grid-cols-4">
        {a.stats.map((s) => (
          <StatCounter key={s.label} {...s} />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/home/StatCounter.tsx frontend/components/home/AboutStats.tsx
git commit -m "feat(home): блок «О магазине» со счётчиками count-up"
```

---

## Task 13: Frontend — модалка консультации (`InquiryModal`)

**Files:**
- Create: `frontend/components/home/InquiryModal.tsx`

**Interfaces:**
- Consumes: `isValidPhone`, `normalizePhone` (существуют в `lib/validation.ts`); BFF `POST /api/inquiry`.
- Produces: `<InquiryModal open, onClose />` — отправляет `{ kind: "consultation", phone, name, message }` в `/api/inquiry`.

- [ ] **Step 1: Создать InquiryModal**

`frontend/components/home/InquiryModal.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { isValidPhone, normalizePhone } from "@/lib/validation";

type InquiryModalProps = { open: boolean; onClose: () => void };
type Status = "idle" | "submitting" | "success" | "error";

export function InquiryModal({ open, onClose }: InquiryModalProps) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const firstFieldRef = useRef<HTMLInputElement>(null);

  // Esc закрывает; фокус — в первое поле при открытии.
  useEffect(() => {
    if (!open) return;
    firstFieldRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Авто-закрытие после успеха.
  useEffect(() => {
    if (status !== "success") return;
    const t = setTimeout(() => {
      onClose();
      setStatus("idle");
      setName("");
      setPhone("");
      setMessage("");
    }, 1800);
    return () => clearTimeout(t);
  }, [status, onClose]);

  if (!open) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (status === "submitting") return;
    if (!name.trim()) {
      setError("Укажите имя.");
      return;
    }
    if (!isValidPhone(phone)) {
      setError("Укажите корректный номер телефона.");
      return;
    }
    setError("");
    setStatus("submitting");
    try {
      const res = await fetch("/api/inquiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "consultation",
          phone: normalizePhone(phone),
          name: name.trim(),
          message: message.trim(),
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setStatus("success");
    } catch {
      setStatus("error");
      setError("Не удалось отправить заявку. Попробуйте ещё раз.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="inquiry-title"
        className="w-full max-w-md rounded-lg border border-line bg-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <h2 id="inquiry-title" className="font-display text-xl font-semibold text-ink">
            Получить консультацию
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-md text-ink-3 hover:bg-raised hover:text-ink"
            aria-label="Закрыть"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        {status === "success" ? (
          <p className="py-6 text-center text-ink-2">
            Спасибо! Мы свяжемся с вами в ближайшее время.
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-3" noValidate>
            <input
              ref={firstFieldRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ваше имя"
              className="w-full rounded-md border border-line bg-canvas px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            />
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Телефон"
              className="w-full rounded-md border border-line bg-canvas px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            />
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Что подобрать? (необязательно)"
              rows={3}
              className="w-full rounded-md border border-line bg-canvas px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            />
            {error && <p className="text-sm text-danger">{error}</p>}
            <button
              type="submit"
              disabled={status === "submitting"}
              className="w-full rounded-md bg-accent px-5 py-3 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
            >
              {status === "submitting" ? "Отправляем…" : "Отправить заявку"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/InquiryModal.tsx
git commit -m "feat(home): модалка консультации с отправкой в /api/inquiry"
```

---

## Task 14: Frontend — композиция главной (`app/page.tsx`) + обвязка модалки

**Files:**
- Create: `frontend/components/home/HomeInteractive.tsx`
- Modify: `frontend/app/page.tsx` (полная замена)

**Interfaces:**
- Consumes: `getCategoryTree`, `getBestsellers` (Task 4); все блоки (Tasks 7–13).
- Produces: главная страница `/`. `HomeInteractive` — client-обёртка, держащая состояние модалки и связывающая Hero/ConsultBlock с `InquiryModal`.

- [ ] **Step 1: Client-обёртка состояния модалки**

`frontend/components/home/HomeInteractive.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { Product } from "@/lib/types";
import type { CategoryNode } from "@/lib/catalog";
import { Hero } from "./Hero";
import { CategoryGrid } from "./CategoryGrid";
import { TrustBadges } from "./TrustBadges";
import { Bestsellers } from "./Bestsellers";
import { ConsultBlock } from "./ConsultBlock";
import { AboutStats } from "./AboutStats";
import { InquiryModal } from "./InquiryModal";

type HomeInteractiveProps = {
  categories: CategoryNode[];
  bestsellers: Product[];
};

export function HomeInteractive({ categories, bestsellers }: HomeInteractiveProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const openModal = () => setModalOpen(true);

  return (
    <>
      <Hero onConsult={openModal} />
      <CategoryGrid categories={categories} />
      <TrustBadges />
      <Bestsellers products={bestsellers} />
      <ConsultBlock onConsult={openModal} />
      <AboutStats />
      <InquiryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
```

- [ ] **Step 2: Заменить `app/page.tsx` на SSR-композицию**

`frontend/app/page.tsx` (полная замена — демо ProductCard удаляется):

```tsx
import { HomeInteractive } from "@/components/home/HomeInteractive";
import { getBestsellers, getCategoryTree } from "@/lib/catalog";

export default async function Home() {
  const [categories, bestsellers] = await Promise.all([getCategoryTree(), getBestsellers()]);
  return (
    <main>
      <HomeInteractive categories={categories} bestsellers={bestsellers} />
    </main>
  );
}
```

- [ ] **Step 3: Типы, линт, сборка**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint && npm run build`
Expected: сборка проходит; страница `/` собирается (данные — `cache: "no-store"`, рендер динамический).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx frontend/components/home/HomeInteractive.tsx
git commit -m "feat(home): сборка главной страницы из блоков, удаление демо ProductCard"
```

---

## Task 15: Адаптив, доступность, reduced-motion, ручная проверка

**Files:**
- Modify: точечно любые `frontend/components/home/*` по итогам проверки.

**Interfaces:**
- Consumes: всё предыдущее. Финальная приёмка.

- [ ] **Step 1: Поднять окружение**

```bash
docker compose up -d db redis web
```

Убедиться, что у Next выставлен `INTERNAL_API_BASE_URL` (иначе категории/хиты пустые — блоки скрыты; валидный, но не финальный режим). Фронт в dev: из `frontend/` — `npm run dev`.

- [ ] **Step 2: Backend-приёмка leads**

Run: `pytest apps/leads -v`
Expected: PASS.

- [ ] **Step 3: Браузерная проверка (skill `browse` или Chrome)**

Открыть `http://localhost:3000/` и проверить:
- Hero: параллакс слоёв при скролле; текст/CTA читаемы; «Получить консультацию» открывает модалку.
- Категории: подгрузились из API, hover-подсветка/зум, stagger-появление; клик ведёт в `/catalog/<slug>`.
- Доверие: reveal при входе во вьюпорт.
- Хиты: карточки из API; стрелки прокручивают; «Смотреть все» → `/catalog`.
- Консультация: «Подобрать инструмент» открывает ту же модалку; «Консультация в MAX» — внешняя ссылка (новая вкладка).
- О магазине: счётчики анимируются один раз.
- Модалка: отправка `consultation` → 201; success-экран; Esc/клик по оверлею закрывают.

- [ ] **Step 4: Reduced-motion**

В DevTools включить `prefers-reduced-motion: reduce` (Rendering → Emulate CSS media). Перезагрузить: параллакс/reveal/count-up/stagger выключены, контент статичен и полностью виден.

- [ ] **Step 5: Адаптив**

Прогнать ширины 375 / 768 / 1280:
- топ-бар/нав-меню сворачиваются в бургер (<lg); бургер открывает меню;
- категории 2→3→6 колонок; хиты — горизонтальная карусель; статистика 2→4 колонки;
- ничего не выходит за вьюпорт, текст контрастен.

- [ ] **Step 6: Регрессия других страниц**

Открыть `/catalog/<любая_категория>`, карточку товара, `/cart`, `/checkout` — убедиться, что обновлённая шапка не сломала вёрстку/навигацию.

- [ ] **Step 7: Зафиксировать правки (если были)**

```bash
git add -A frontend/components/home frontend/components/layout
git commit -m "fix(home): полировка адаптива и доступности по итогам ручной проверки"
```

(Если правок не потребовалось — шаг пропустить.)

---

## Самопроверка плана (выполнено автором)

- **Покрытие спеки:** шапка (T6), 7 блоков (Hero T7, Категории T8, Доверие T9, Хиты T10, Консультация T11, О магазине T12), модалка+leads (T1–T2, T13), данные из API (T4), конфиг (T3), motion+reduced-motion (T5, T15), адаптив/a11y/проверка (T15). Backend-расширение consultation (T1–T2) закрывает блокер формы.
- **Плейсхолдеры:** TODO/«позже»/«реализовать потом» в шагах нет; весь код приведён целиком. Плейсхолдеры-ассеты (SVG, градиенты) — намеренные и отмечены как заглушки дизайнера в рамках согласованного объёма.
- **Согласованность типов:** `CategoryNode` определён в T4 (adapters), реэкспортируется из `lib/catalog`, потребляется в T8/T14; `Product` — существующий тип; `HomeStat` — из T3, потребляется в T12; `create_inquiry(product=None)` (T1) ↔ сериализатор (T2) ↔ модалка шлёт `kind:"consultation"` без product (T13); `onConsult: () => void` единообразно в Hero (T7), ConsultBlock (T11), HomeInteractive (T14).
- **Вне объёма (из спеки):** страницы меню/ЛК (заглушки `#`), backend-флаг «хит», финальная графика, сворачивание топ-бара — не реализуются.
