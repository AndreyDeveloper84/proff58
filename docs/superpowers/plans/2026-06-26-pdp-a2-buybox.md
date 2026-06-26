# PDP A — План 2: блок покупки (frontend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести блок покупки карточки товара: выбор количества, обработка состояния «под заказ», реальные заявки «Запросить цену»/«Уточнить поступление» через модалку (→ BFF `/api/inquiry` из Плана 1), липкая панель покупки при скролле.

**Architecture:** Маленькие клиентские компоненты-острова с чёткими интерфейсами. `QuantityStepper` — презентационный контролируемый счётчик. `InquiryDialog` — модалка заявки (fetch → `/api/inquiry`). `OrderCta` (переписан) — оркестрирует: для `in`/`order` реальное добавление в корзину с выбранным количеством, для нет-цены/`out` открывает `InquiryDialog`. `StickyBuyBar` — липкая панель (IntersectionObserver по якорю основного блока), переиспользует `ProductPrice` и `OrderCta`. Бизнес-логики на фронте минимум; создание заявки валидируется на бэке (План 1).

**Tech Stack:** Next.js 16.2.9 (App Router), React 19.2.4, TypeScript 5, Tailwind v4, lucide-react, class-variance-authority. BFF `/api/inquiry` уже есть.

## Global Constraints

- **Next.js здесь с breaking changes** — перед правкой читать релевантный гайд в `frontend/node_modules/next/dist/docs/` (см. `frontend/AGENTS.md`). Не полагаться на знания старого Next по памяти.
- **Тест-раннера во фронте НЕТ** (конвенция репозитория — фронт без юнит-тестов). Верификация каждой задачи: `cd frontend && npx tsc --noEmit` (типы чисто) и `cd frontend && npm run lint` (eslint чисто). Где возможно — ручная проверка в браузере/через curl. Новый тест-стек НЕ вводить.
- **Клиентские компоненты** помечать `"use client"`.
- **Стиль/токены:** Tailwind-токены проекта (`text-ink`, `text-ink-2`, `text-ink-3`, `bg-surface`, `bg-raised`, `border-line`, `bg-accent`, `text-accent-ink`, `text-accent`); утилита `cn` из `@/lib/utils`; компонент `Button` из `@/components/ui/button` (variant: accent|outline|ghost, size: default|sm|icon).
- **Доступность:** интерактив с клавиатуры, `aria-*`, фокус-трап и Esc в модалке.
- **Существующие интерфейсы:**
  - `useCart()` из `@/components/cart/CartProvider` → `add(productId: number, quantity?: number): Promise<Cart>`.
  - `ApiError` из `@/lib/api`.
  - `StockState` из `@/lib/types` = `"in" | "out" | "order"`.
  - `ProductPrice` из `@/components/product/ProductPrice` (props `{ price: Product["price"] }`).
- **Комментарии — на русском.**

---

### Task 1: `QuantityStepper` — контролируемый счётчик количества

**Files:**
- Create: `frontend/components/product/QuantityStepper.tsx`

**Interfaces:**
- Produces: `QuantityStepper` — props `{ value: number; max?: number; min?: number; onChange: (next: number) => void; disabled?: boolean; id?: string }`. Кнопки −/+ и числовой input; кламп в `[min ?? 1, max ?? ∞]`. Чистый презентационный компонент (не знает про корзину).

- [ ] **Step 1: Прочитать гайд Next (клиентские компоненты)**

Открыть и просмотреть `frontend/node_modules/next/dist/docs/` на предмет актуальных правил клиентских компонентов/инпутов (см. `frontend/AGENTS.md`). Это требование Global Constraints.

- [ ] **Step 2: Реализовать компонент**

Создать `frontend/components/product/QuantityStepper.tsx`:

```tsx
"use client";

import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

// Контролируемый счётчик количества для блока покупки. Презентационный: не знает
// о корзине, только сообщает наружу новое значение через onChange. Кламп в [min, max].
export function QuantityStepper({
  value,
  max,
  min = 1,
  onChange,
  disabled = false,
  id,
}: {
  value: number;
  max?: number;
  min?: number;
  onChange: (next: number) => void;
  disabled?: boolean;
  id?: string;
}) {
  const clamp = (n: number) => {
    if (Number.isNaN(n)) return min;
    const lo = Math.max(min, n);
    return max != null ? Math.min(max, lo) : lo;
  };

  const set = (n: number) => onChange(clamp(n));

  return (
    <div className={cn("inline-flex items-center rounded-md border border-line bg-surface")}>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => set(value - 1)}
        disabled={disabled || value <= min}
        aria-label="Уменьшить количество"
      >
        <Minus className="h-4 w-4" aria-hidden />
      </button>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        className="h-9 w-12 bg-transparent text-center text-sm text-ink outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => set(parseInt(e.target.value, 10))}
        aria-label="Количество"
      />
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => set(value + 1)}
        disabled={disabled || (max != null && value >= max)}
        aria-label="Увеличить количество"
      >
        <Plus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Проверка типов и линта**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: без ошибок (предупреждений по новому файлу нет).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/product/QuantityStepper.tsx
git commit -m "feat(pdp): QuantityStepper — счётчик количества"
```

---

### Task 2: `InquiryDialog` — модалка заявки (→ /api/inquiry)

**Files:**
- Create: `frontend/components/product/InquiryDialog.tsx`

**Interfaces:**
- Consumes: BFF `POST /api/inquiry` (тело `{ kind, product, phone, name?, message? }`, ответ `201 {id,kind,status}` или `400`).
- Produces: `InquiryDialog` — props `{ open: boolean; onClose: () => void; productId: number; kind: "price_request" | "restock_notify"; title: string }`. Поля: телефон (обязателен), имя, сообщение. Состояния idle/submitting/success/error. Фокус-трап, Esc, клик по оверлею закрывает (кроме submitting).

- [ ] **Step 1: Прочитать гайд Next (порталы/эффекты/события клавиатуры в клиентских компонентах)**

Просмотреть `frontend/node_modules/next/dist/docs/` по части клиентских компонентов и работы с `useEffect`/событиями. (Global Constraints.)

- [ ] **Step 2: Реализовать модалку**

Создать `frontend/components/product/InquiryDialog.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Phase = "idle" | "submitting" | "success" | "error";

// Модалка заявки по товару: «Запросить цену» / «Уточнить поступление».
// Отправляет в BFF /api/inquiry (далее Django /api/leads/inquiries/). Валидация
// телефона — на бэке; здесь только обязательность поля и UX-состояния.
export function InquiryDialog({
  open,
  onClose,
  productId,
  kind,
  title,
}: {
  open: boolean;
  onClose: () => void;
  productId: number;
  kind: "price_request" | "restock_notify";
  title: string;
}) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const dialogRef = useRef<HTMLDivElement>(null);

  // Esc закрывает (кроме отправки); блокируем скролл фона, пока открыто.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase !== "submitting") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, phase, onClose]);

  // Фокус на первое поле при открытии.
  useEffect(() => {
    if (open) dialogRef.current?.querySelector("input")?.focus();
  }, [open]);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone.trim() || phase === "submitting") return;
    setPhase("submitting");
    try {
      const res = await fetch("/api/inquiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, product: productId, phone, name, message }),
      });
      setPhase(res.ok ? "success" : "error");
    } catch {
      setPhase("error");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => phase !== "submitting" && onClose()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-sm rounded-lg border border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="text-ink-3 hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        {phase === "success" ? (
          <p className="text-sm text-ink-2">
            Заявка отправлена — мы свяжемся с вами по телефону.
          </p>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <input
              type="tel"
              required
              placeholder="Телефон*"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-accent"
            />
            <input
              type="text"
              placeholder="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-accent"
            />
            <textarea
              placeholder="Комментарий"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
            {phase === "error" && (
              <p className="text-xs text-red-600">
                Не удалось отправить. Проверьте телефон и попробуйте ещё раз.
              </p>
            )}
            <Button type="submit" variant="accent" disabled={phase === "submitting"}>
              {phase === "submitting" && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              )}
              Отправить
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Проверка типов и линта**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/product/InquiryDialog.tsx
git commit -m "feat(pdp): InquiryDialog — модалка заявки (→ /api/inquiry)"
```

---

### Task 3: Переписать `OrderCta` — количество, «под заказ», заявки

**Files:**
- Modify: `frontend/components/product/OrderCta.tsx` (полная замена содержимого)

**Interfaces:**
- Consumes: `QuantityStepper` (Task 1), `InquiryDialog` (Task 2), `useCart().add`, `ApiError`, `StockState`.
- Produces: `OrderCta` — props без изменений: `{ productId: number; stock?: StockState; hasPrice?: boolean }`. Поведение:
  - нет цены → кнопка «Запросить цену» открывает `InquiryDialog kind="price_request"`.
  - `stock="out"` → кнопка «Уточнить поступление» открывает `InquiryDialog kind="restock_notify"`.
  - `stock="in"` или `"order"` → `QuantityStepper` + кнопка добавления в корзину (`add(productId, qty)`); текст для `order` — «Под заказ», для `in` — «В корзину».

- [ ] **Step 1: Прочитать гайд Next (клиентские компоненты, состояние)**

Просмотреть `frontend/node_modules/next/dist/docs/` (Global Constraints).

- [ ] **Step 2: Полностью заменить `OrderCta.tsx`**

Заменить содержимое `frontend/components/product/OrderCta.tsx` на:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, Check, FileText, Loader2, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import type { StockState } from "@/lib/types";
import { QuantityStepper } from "./QuantityStepper";
import { InquiryDialog } from "./InquiryDialog";

// CTA карточки товара (PDP). Сценарии:
//   нет цены        → «Запросить цену»     → модалка заявки (price_request)
//   нет в наличии   → «Уточнить поступление» → модалка заявки (restock_notify)
//   in / order      → выбор количества + добавление в корзину (под заказ — тот же поток)
export function OrderCta({
  productId,
  stock = "in",
  hasPrice = true,
}: {
  productId: number;
  stock?: StockState;
  hasPrice?: boolean;
}) {
  const [dialog, setDialog] = useState<null | "price_request" | "restock_notify">(null);

  if (!hasPrice) {
    return (
      <>
        <Button
          variant="accent"
          onClick={() => setDialog("price_request")}
          data-event="request_price"
          data-product-id={productId}
        >
          <FileText className="h-4 w-4" aria-hidden />
          Запросить цену
        </Button>
        <InquiryDialog
          open={dialog === "price_request"}
          onClose={() => setDialog(null)}
          productId={productId}
          kind="price_request"
          title="Запросить цену"
        />
      </>
    );
  }

  if (stock === "out") {
    return (
      <>
        <Button
          variant="outline"
          onClick={() => setDialog("restock_notify")}
          data-event="notify_restock"
          data-product-id={productId}
        >
          <Bell className="h-4 w-4" aria-hidden />
          Уточнить поступление
        </Button>
        <InquiryDialog
          open={dialog === "restock_notify"}
          onClose={() => setDialog(null)}
          productId={productId}
          kind="restock_notify"
          title="Уточнить поступление"
        />
      </>
    );
  }

  return <AddToCartCta productId={productId} isOrder={stock === "order"} />;
}

type Phase = "idle" | "loading" | "added" | "error";

function AddToCartCta({ productId, isOrder }: { productId: number; isOrder: boolean }) {
  const { add } = useCart();
  const [qty, setQty] = useState(1);
  const [phase, setPhase] = useState<Phase>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const handleClick = async () => {
    if (phase === "loading") return;
    setPhase("loading");
    try {
      await add(productId, qty);
      setPhase("added");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setPhase("idle"), 1800);
    } catch (err) {
      setPhase("error");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setPhase("idle"), 2500);
      if (!(err instanceof ApiError)) console.error(err);
    }
  };

  const label = isOrder ? "Под заказ" : "В корзину";

  return (
    <div className="flex items-center gap-3">
      <QuantityStepper value={qty} min={1} onChange={setQty} disabled={phase === "loading"} />
      <Button
        variant="accent"
        disabled={phase === "loading"}
        onClick={handleClick}
        data-event="add_to_cart_from_pdp"
        data-product-id={productId}
      >
        {phase === "loading" ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : phase === "added" ? (
          <Check className="h-4 w-4" aria-hidden />
        ) : (
          <ShoppingCart className="h-4 w-4" aria-hidden />
        )}
        {phase === "added" ? "Добавлено" : phase === "error" ? "Ошибка, повторить" : label}
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Проверка типов и линта**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/product/OrderCta.tsx
git commit -m "feat(pdp): OrderCta — количество, под заказ, заявки через модалку"
```

---

### Task 4: `StickyBuyBar` — липкая панель покупки + интеграция в страницу

**Files:**
- Create: `frontend/components/product/StickyBuyBar.tsx`
- Modify: `frontend/app/product/[slug]/page.tsx` (обернуть основной блок покупки якорем и добавить `StickyBuyBar`)

**Interfaces:**
- Consumes: `ProductPrice`, `OrderCta` (Task 3), `Product`, `StockState`.
- Produces: `StickyBuyBar` — props `{ product: Pick<Product, "id" | "name" | "price" | "stock"> }`. Появляется снизу экрана, когда основной блок покупки ушёл из вьюпорта; следит через IntersectionObserver по элементу-якорю с `id="buybox-anchor"`.

- [ ] **Step 1: Прочитать гайд Next (клиентские компоненты, IntersectionObserver/refs)**

Просмотреть `frontend/node_modules/next/dist/docs/` (Global Constraints).

- [ ] **Step 2: Реализовать StickyBuyBar**

Создать `frontend/components/product/StickyBuyBar.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import type { Product } from "@/lib/types";
import { ProductPrice } from "./ProductPrice";
import { OrderCta } from "./OrderCta";

// Липкая панель покупки: показывается, когда основной блок (#buybox-anchor) ушёл из
// вьюпорта при скролле. На мобиле фиксирована снизу. Переиспользует ProductPrice/OrderCta.
export function StickyBuyBar({
  product,
}: {
  product: Pick<Product, "id" | "name" | "price" | "stock">;
}) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const anchor = document.getElementById("buybox-anchor");
    if (!anchor) return;
    const obs = new IntersectionObserver(
      ([entry]) => setShown(!entry.isIntersecting),
      { threshold: 0 },
    );
    obs.observe(anchor);
    return () => obs.disconnect();
  }, []);

  if (!shown) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-ink-2">{product.name}</p>
          <ProductPrice price={product.price} />
        </div>
        <OrderCta
          productId={product.id}
          stock={product.stock}
          hasPrice={product.price.final != null}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Подключить якорь и панель в странице товара**

В `frontend/app/product/[slug]/page.tsx`:

1. Добавить импорт рядом с прочими импортами компонентов:

```tsx
import { StickyBuyBar } from "@/components/product/StickyBuyBar";
```

2. Обернуть существующий блок цены/CTA элементом-якорем — найти блок:

```tsx
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-4">
            <ProductPrice price={product.price} />
            <OrderCta
              productId={product.id}
              stock={product.stock}
              hasPrice={product.price.final != null}
            />
          </div>
```

и добавить ему `id="buybox-anchor"`:

```tsx
          <div
            id="buybox-anchor"
            className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-4"
          >
            <ProductPrice price={product.price} />
            <OrderCta
              productId={product.id}
              stock={product.stock}
              hasPrice={product.price.final != null}
            />
          </div>
```

3. Перед закрывающим `</div>` корневого контейнера страницы (после блока `CompatibilitySections`) добавить панель:

```tsx
      <div className="mt-10">
        <CompatibilitySections sections={product.compatible} />
      </div>

      <StickyBuyBar product={product} />
    </div>
  );
}
```

- [ ] **Step 4: Проверка типов и линта**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/product/StickyBuyBar.tsx frontend/app/product/[slug]/page.tsx
git commit -m "feat(pdp): StickyBuyBar — липкая панель покупки при скролле"
```

---

## Финальная проверка Плана 2

- [ ] `cd frontend && npx tsc --noEmit` — без ошибок типов.
- [ ] `cd frontend && npm run lint` — без ошибок.
- [ ] (Если поднят dev-фронт) Ручная проверка на товаре staging: счётчик меняет количество и оно уходит в корзину; «Запросить цену»/«Уточнить поступление» открывают модалку, отправка даёт «Заявка отправлена»; при скролле появляется липкая панель.

## Self-review (соответствие спеку, часть «блок покупки»)

- Выбор количества (`QuantityStepper`, проброс qty в `add`) — Task 1 + Task 3. ✓
- Состояние `order` («Под заказ») — Task 3. ✓
- Реальные заявки price_request/restock_notify через модалку → `/api/inquiry` — Task 2 + Task 3. ✓
- Sticky-панель при скролле (IntersectionObserver) — Task 4. ✓
- Доступность модалки (Esc, фокус, aria-modal) — Task 2. ✓

## Зависимости

- Требует Плана 1 (BFF `/api/inquiry` + Django `apps/leads`) — уже выполнен на ветке `claude/pdp-polish-a`.

## Дальше

- **План 3:** галерея (клавиатура/свайп/lightbox/lazy).
- **План 4:** контент/SEO (Product JSON-LD, Collapsible, Share) + a11y-аудит и регрессия.
