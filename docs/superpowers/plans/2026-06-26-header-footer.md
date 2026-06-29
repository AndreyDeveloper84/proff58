# Шапка + подвал витрины — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Обогатить шапку (две строки: инфо-панель + основная) и добавить подвал
витрины, визуально сблизив `/catalog` и весь сайт с макетом `list_products_main.png`.

**Architecture:** Весь контент — из одного фронт-конфига `frontend/lib/site.ts`
(чистые данные, имена иконок строками). `Footer` — серверный компонент, `Header`
+ `TopBar` — клиентские (Header использует `useCart`). Иконки маппятся из строковых
ключей внутри компонентов (`lib/site.ts` без JSX). Бэкенд/данные не трогаем.

**Tech Stack:** Next.js (App Router), TypeScript, Tailwind v4 (бренд-токены),
lucide-react.

## Global Constraints

- Только существующие бренд-токены: `bg-canvas`/`surface`/`raised`, `border-line`,
  `text-ink`/`-2`/`-3`, `text-accent`, `text-accent-ink`, `font-display`. Произвольные
  hex-цвета не вводить.
- Иконки — только `lucide-react`.
- `frontend/lib/site.ts` — **чистые данные**, без JSX/React-импортов.
- Значения контента — плейсхолдеры из макета, каждое спорное помечать `// TODO: SiteSettings`.
- Проверка каждой задачи: из `frontend/` запустить `npx tsc --noEmit` (зелёно) и
  `npm run lint` (без новых ошибок). Юнит-тесты не заводим (статичная презентация).
- Коммиты — Conventional Commits, на ветке `claude/pdp-polish-a`.

---

### Task 1: Конфиг контента `lib/site.ts`

**Files:**
- Create: `frontend/lib/site.ts`

**Interfaces:**
- Produces: `export const SITE` со структурой ниже; типы выводятся через `as const`.
  Ключи иконок: `trustBadges[].icon`, `socials[].icon` — строки, маппятся в компонентах.

- [ ] **Step 1: Создать файл с конфигом**

```ts
// Единый источник контента шапки/подвала. Чистые данные (без JSX).
// TODO: в будущем заменить на данные из SiteSettings.contacts/requisites через BFF.
export const SITE = {
  brand: { name: "Профессионал", tagline: "территория инструмента" },
  region: "Пенза",
  phone: { display: "8 (800) 600-44-99", href: "tel:+78006004499" },
  schedule: "Пн–Вс 9:00–20:00",
  email: "info@proff58.ru", // TODO: SiteSettings
  address: "г. Пенза, ул. Складская, 10", // TODO: SiteSettings

  // Верхнее меню инфо-панели.
  topNav: [
    { label: "Акции", href: "/promo" }, // TODO: маршруты-заглушки
    { label: "Доставка и оплата", href: "/delivery" },
    { label: "Гарантия", href: "/warranty" },
    { label: "Сервис", href: "/service" },
    { label: "Компания", href: "/about" },
    { label: "Контакты", href: "/contacts" },
  ],

  // Иконка — строковый ключ (маппинг в Footer): shield|truck|undo|wrench|gift.
  trustBadges: [
    { icon: "shield", label: "Официальная гарантия" },
    { icon: "truck", label: "Быстрая доставка" },
    { icon: "undo", label: "Возврат за 14 дней" },
    { icon: "wrench", label: "Сервисный центр" },
    { icon: "gift", label: "Программа лояльности" },
  ],

  footerColumns: [
    {
      title: "Каталог",
      links: [
        { label: "Электроинструмент", href: "/catalog" },
        { label: "Бензоинструмент", href: "/catalog" },
        { label: "Садовая техника", href: "/catalog" },
        { label: "Оснастка", href: "/catalog" },
      ],
    },
    {
      title: "Покупателю",
      links: [
        { label: "Доставка и оплата", href: "/delivery" },
        { label: "Гарантия", href: "/warranty" },
        { label: "Возврат", href: "/returns" },
        { label: "Вопросы и ответы", href: "/faq" },
      ],
    },
    {
      title: "Компания",
      links: [
        { label: "О магазине", href: "/about" },
        { label: "Контакты", href: "/contacts" },
        { label: "Сервисный центр", href: "/service" },
        { label: "Вакансии", href: "/jobs" },
      ],
    },
  ],

  // Иконка — строковый ключ (маппинг в Footer): vk|telegram|youtube|whatsapp.
  socials: [
    { label: "ВКонтакте", href: "https://vk.com/", icon: "vk" }, // TODO
    { label: "Telegram", href: "https://t.me/", icon: "telegram" },
    { label: "YouTube", href: "https://youtube.com/", icon: "youtube" },
  ],

  payments: ["Картой онлайн", "Наличными", "Безналичный (B2B)", "При получении"],
} as const;
```

- [ ] **Step 2: Проверить типы**

Run (из `frontend/`): `npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/site.ts
git commit -m "feat(storefront): конфиг контента шапки/подвала (lib/site.ts)"
```

---

### Task 2: Подвал `Footer.tsx` + подключение в layout

**Files:**
- Create: `frontend/components/layout/Footer.tsx`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: `SITE` из `@/lib/site`.
- Produces: `export function Footer()` — серверный компонент без пропсов.

- [ ] **Step 1: Создать Footer**

```tsx
import Link from "next/link";
import {
  ShieldCheck,
  Truck,
  Undo2,
  Wrench,
  Gift,
  Phone,
  Mail,
  MapPin,
  Clock,
  Send,
  Youtube,
  type LucideIcon,
} from "lucide-react";
import { SITE } from "@/lib/site";

// Маппинг строковых ключей конфига в иконки (lib/site.ts — без JSX).
const TRUST_ICONS: Record<string, LucideIcon> = {
  shield: ShieldCheck,
  truck: Truck,
  undo: Undo2,
  wrench: Wrench,
  gift: Gift,
};
const SOCIAL_ICONS: Record<string, LucideIcon> = {
  telegram: Send,
  youtube: Youtube,
  vk: Send, // у lucide нет бренд-иконки VK → нейтральная заглушка
};

export function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-surface">
      {/* Trust-бейджи */}
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-4 px-4 py-6 sm:grid-cols-3 lg:grid-cols-5 sm:px-6 lg:px-8">
        {SITE.trustBadges.map((b) => {
          const Icon = TRUST_ICONS[b.icon] ?? ShieldCheck;
          return (
            <div key={b.label} className="flex items-center gap-2 text-sm text-ink-2">
              <Icon className="h-5 w-5 shrink-0 text-accent" aria-hidden />
              {b.label}
            </div>
          );
        })}
      </div>

      <div className="border-t border-line">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 px-4 py-8 md:grid-cols-4 sm:px-6 lg:px-8">
          {/* Колонки ссылок */}
          {SITE.footerColumns.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h3 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-ink">
                {col.title}
              </h3>
              <ul className="space-y-2">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="text-sm text-ink-2 hover:text-accent">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}

          {/* Колонка контактов */}
          <div>
            <h3 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-ink">
              Контакты
            </h3>
            <ul className="space-y-2 text-sm text-ink-2">
              <li>
                <a href={SITE.phone.href} className="flex items-center gap-2 hover:text-accent">
                  <Phone className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                  {SITE.phone.display}
                </a>
              </li>
              <li className="flex items-center gap-2">
                <Clock className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                {SITE.schedule}
              </li>
              <li>
                <a href={`mailto:${SITE.email}`} className="flex items-center gap-2 hover:text-accent">
                  <Mail className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                  {SITE.email}
                </a>
              </li>
              <li className="flex items-center gap-2">
                <MapPin className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                {SITE.address}
              </li>
            </ul>
            {/* Соцсети */}
            <div className="mt-4 flex gap-2">
              {SITE.socials.map((s) => {
                const Icon = SOCIAL_ICONS[s.icon] ?? Send;
                return (
                  <a
                    key={s.label}
                    href={s.href}
                    aria-label={s.label}
                    className="grid h-9 w-9 place-items-center rounded-md border border-line text-ink-2 transition hover:border-accent hover:text-accent"
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                  </a>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Оплата + копирайт */}
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-5 text-xs text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <div className="flex flex-wrap gap-2">
            {SITE.payments.map((p) => (
              <span key={p} className="rounded-md border border-line bg-raised px-2 py-1">
                {p}
              </span>
            ))}
          </div>
          <span>
            © 2026 {SITE.brand.name} · {SITE.region}
          </span>
        </div>
      </div>
    </footer>
  );
}
```

- [ ] **Step 2: Подключить Footer в layout с прижатием к низу**

В `frontend/app/layout.tsx`: добавить импорт и обернуть контент. Текущий `body`
содержит `<CartProvider><Header />{children}</CartProvider>`. Заменить тело
`CartProvider` на флекс-колонку:

```tsx
import { Footer } from "@/components/layout/Footer";
// ...
        <CartProvider>
          <div className="flex min-h-screen flex-col">
            <Header />
            <main className="flex-1">{children}</main>
            <Footer />
          </div>
        </CartProvider>
```

(Импорт `Footer` добавить рядом с импортом `Header`.)

- [ ] **Step 3: Проверить типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/layout/Footer.tsx frontend/app/layout.tsx
git commit -m "feat(storefront): подвал витрины (Footer) + sticky-footer в layout"
```

---

### Task 3: Инфо-панель `TopBar.tsx`

**Files:**
- Create: `frontend/components/layout/TopBar.tsx`

**Interfaces:**
- Consumes: `SITE` из `@/lib/site`.
- Produces: `export function TopBar()` — без пропсов; рендерится внутри `Header`.

- [ ] **Step 1: Создать TopBar**

```tsx
import Link from "next/link";
import { MapPin, Phone, Clock, Heart, GitCompare, User } from "lucide-react";
import { SITE } from "@/lib/site";

// Верхняя инфо-панель шапки. Иконки «Избранное»/«Сравнение» — визуальные
// (без перехода): рабочих роутов нет, persistence — отдельная задача (P2).
export function TopBar() {
  return (
    <div className="border-b border-line bg-surface text-xs text-ink-3">
      <div className="mx-auto flex h-9 max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <span className="hidden items-center gap-1 sm:flex">
          <MapPin className="h-3.5 w-3.5 text-accent" aria-hidden />
          {SITE.region}
        </span>

        <nav aria-label="Информация" className="hidden gap-4 md:flex">
          {SITE.topNav.map((l) => (
            <Link key={l.label} href={l.href} className="hover:text-accent">
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <a href={SITE.phone.href} className="flex items-center gap-1 font-medium text-ink hover:text-accent">
            <Phone className="h-3.5 w-3.5 text-accent" aria-hidden />
            {SITE.phone.display}
          </a>
          <span className="hidden items-center gap-1 lg:flex">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            {SITE.schedule}
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Избранное"
              title="Избранное"
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:text-accent"
            >
              <Heart className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Сравнение"
              title="Сравнение"
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:text-accent"
            >
              <GitCompare className="h-4 w-4" aria-hidden />
            </button>
            <Link
              href="/account"
              aria-label="Вход в личный кабинет"
              title="Вход"
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:text-accent"
            >
              <User className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Проверить типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/layout/TopBar.tsx
git commit -m "feat(storefront): верхняя инфо-панель шапки (TopBar)"
```

---

### Task 4: Основная строка шапки `Header.tsx`

**Files:**
- Modify: `frontend/components/layout/Header.tsx` (полная замена содержимого)

**Interfaces:**
- Consumes: `TopBar` из `./TopBar`, `SearchBar` из `./SearchBar`, `useCart` из
  `@/components/cart/CartProvider`, `SITE` из `@/lib/site`.
- Produces: `export function Header()` — клиентский компонент (без пропсов).

- [ ] **Step 1: Заменить содержимое Header**

```tsx
"use client";

import Link from "next/link";
import { ShoppingCart, LayoutGrid } from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { SITE } from "@/lib/site";
import { TopBar } from "./TopBar";
import { SearchBar } from "./SearchBar";

export function Header() {
  const { count } = useCart();

  return (
    <header className="sticky top-0 z-40 bg-canvas/95 backdrop-blur">
      <TopBar />
      <div className="border-b border-line">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/" className="shrink-0 leading-tight">
            <span className="block font-display text-xl font-bold uppercase tracking-wide text-accent">
              {SITE.brand.name}
            </span>
            <span className="hidden text-[10px] uppercase tracking-wide text-ink-3 sm:block">
              {SITE.brand.tagline}
            </span>
          </Link>

          <Link
            href="/catalog"
            className="hidden shrink-0 items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:opacity-90 sm:flex"
          >
            <LayoutGrid className="h-4 w-4" aria-hidden />
            Весь каталог
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
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Проверить типы и линт**

Run (из `frontend/`): `npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/layout/Header.tsx
git commit -m "feat(storefront): двухстрочная шапка с кнопкой «Весь каталог»"
```

---

### Task 5: Сборка и визуальная проверка

**Files:** —

- [ ] **Step 1: Прод-сборка фронта**

Run (из `frontend/`): `npm run build`
Expected: сборка завершается без ошибок типов/линта; маршруты собраны.

- [ ] **Step 2: Визуальная сверка (по желанию)**

Поднять dev-сервер фронта (`npm run dev`) и открыть `/` и `/catalog`. Сверить с
`list_products_main.png`: две строки шапки (регион/телефон/график/меню/иконки +
логотип/«Весь каталог»/поиск/корзина) и подвал (trust-бейджи, 4 колонки, оплата,
соцсети, копирайт), подвал прижат к низу. Тёмная тема, бренд-токены.

- [ ] **Step 3: Финальный коммит (если были правки после сверки)**

```bash
git add -A
git commit -m "chore(storefront): полировка шапки/подвала по макету"
```

---

## Self-Review

- **Покрытие спеки:** `lib/site.ts` (Task 1) ✓; `Footer.tsx` (Task 2) ✓;
  `TopBar.tsx` (Task 3) ✓; `Header.tsx` две строки + «Весь каталог»→/catalog
  (Task 4) ✓; `layout.tsx` Footer + sticky-flex (Task 2) ✓; иконки избранное/
  сравнение визуальные (Task 3) ✓; деплой — отдельный отчёт (вне плана) ✓.
- **Плейсхолдеры:** контент-плейсхолдеры помечены `// TODO: SiteSettings` намеренно;
  «как сделать» показано кодом в каждом шаге — нет процедурных заглушек.
- **Согласованность типов:** `SITE` определён в Task 1, потребляется по тем же
  ключам в Tasks 2–4; иконки маппятся по строковым ключам `trustBadges[].icon`/
  `socials[].icon` внутри `Footer`. `Header`→`TopBar`/`SearchBar`/`useCart` —
  имена совпадают с существующими модулями.
