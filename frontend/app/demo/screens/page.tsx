import { Search } from "lucide-react";

import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";
import { ProductCard } from "@/components/product/ProductCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, SuccessState } from "@/components/ui/states";
import { Textarea } from "@/components/ui/textarea";

import { ThemeFrame } from "../_components/ThemeFrame";
import { MOCK_CATEGORIES, MOCK_FACETS, MOCK_PRODUCTS } from "./mocks";

// Галерея макетов ключевых экранов MVP (#40). Статичные шаблоны из SP2-кита —
// эталон вёрстки (desktop/mobile-адаптив + состояния), без живых данных и прод-навигации.

function Screen({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-display text-xl text-ink">{title}</h2>
        {note && <p className="text-sm text-ink-3">{note}</p>}
      </div>
      <div className="overflow-hidden rounded-lg border border-line bg-canvas">{children}</div>
    </section>
  );
}

function MiniHeader() {
  return (
    <div className="flex items-center gap-4 border-b border-line bg-surface px-4 py-3">
      <span className="font-display text-lg text-ink">Профессионал</span>
      <div className="hidden flex-1 sm:block">
        {/* Поиск (mock): иконка + placeholder — читается как поле поиска. */}
        <div className="flex h-9 items-center gap-2 rounded-md border border-line bg-canvas px-3 text-ink-3">
          <Search className="h-4 w-4" aria-hidden />
          <span className="text-sm">Поиск по каталогу…</span>
        </div>
      </div>
      <Button size="sm" variant="ghost" className="ml-auto">
        Каталог
      </Button>
      <Button size="sm" variant="outline">
        Корзина
      </Button>
    </div>
  );
}

export default function ScreensPage() {
  const [hit, order, out] = MOCK_PRODUCTS;

  return (
    <ThemeFrame>
      <div className="mx-auto max-w-5xl space-y-12 p-6">
      <header className="space-y-1">
        <h1 className="font-display text-2xl text-ink">MVP · Макеты экранов</h1>
        <p className="text-sm text-ink-2">
          Ключевые сценарии витрины, собранные из SP2-компонентов. Раскладка адаптивна
          (desktop/mobile), состояния наличия / пусто / ошибка / загрузка отражены.
        </p>
      </header>

      {/* 1. Главная / категории */}
      <Screen title="1. Главная / категории" note="Hero + сетка категорий (mobile: 2 колонки, desktop: 3)">
        <MiniHeader />
        <div className="space-y-6 p-4">
          <Card surface="raised" pad="lg" className="text-center">
            <p className="font-display text-2xl text-ink">Инструмент для профессионалов</p>
            <p className="mt-1 text-sm text-ink-2">Доставка по Пензе и области</p>
            <Button className="mt-4">В каталог</Button>
          </Card>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {MOCK_CATEGORIES.map((c) => (
              <Card key={c} pad="md" className="flex items-center justify-between">
                <span className="text-sm text-ink">{c}</span>
                <span className="text-ink-3">→</span>
              </Card>
            ))}
          </div>
        </div>
      </Screen>

      {/* 2. Каталог (PLP) с фасетами */}
      <Screen
        title="2. Список товаров с фасетами (PLP)"
        note="Sidebar фасетов (desktop) / bottom-sheet (mobile) + сетка карточек"
      >
        <MiniHeader />
        <div className="grid gap-4 p-4 lg:grid-cols-[220px_1fr]">
          <aside className="hidden space-y-4 lg:block">
            {MOCK_FACETS.map((f) => (
              <Card key={f.title} pad="sm">
                <p className="mb-2 text-sm font-semibold text-ink">{f.title}</p>
                <ul className="space-y-1">
                  {f.options.map((o) => (
                    <li key={o} className="flex items-center gap-2 text-sm text-ink-2">
                      <span className="h-3.5 w-3.5 rounded-sm border border-line" />
                      {o}
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </aside>
          <div>
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm text-ink-2">Найдено 105 товаров</span>
              <Button size="sm" variant="outline" className="lg:hidden">
                Фильтры
              </Button>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <ProductCard product={hit} />
              <ProductCard product={order} />
              <ProductCard product={out} />
            </div>
          </div>
        </div>
      </Screen>

      {/* 2b. Состояния PLP */}
      <Screen
        title="2б. Состояния списка"
        note="loading контентной зоны — skeleton (не спиннер); пусто / ошибка"
      >
        <div className="space-y-4 p-4">
          {/* Загрузка контентной зоны PLP — через skeleton карточек. */}
          <ProductGridSkeleton count={4} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Card pad="none">
              <EmptyState
                title="Ничего не найдено"
                description="Сбросьте часть фильтров."
                action={<Button variant="outline">Сбросить</Button>}
              />
            </Card>
            <Card pad="none">
              <ErrorState action={<Button variant="outline">Повторить</Button>} />
            </Card>
          </div>
        </div>
      </Screen>

      {/* 3. Карточка товара (PDP) */}
      <Screen title="3. Карточка товара" note="Галерея + характеристики + покупка (mobile: стек, desktop: 2 колонки)">
        <MiniHeader />
        <div className="grid gap-6 p-4 lg:grid-cols-2">
          <div className="aspect-square rounded-lg bg-photo" />
          <div className="space-y-4">
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="hit">Хит</Badge>
              <Badge variant="sale">−16%</Badge>
            </div>
            <h3 className="font-display text-xl text-ink">{hit.name}</h3>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-ink">12 990 ₽</span>
              <span className="text-sm text-ink-3 line-through">15 490 ₽</span>
            </div>
            <p className="text-sm text-brand">В наличии · {hit.stockQty} шт</p>
            <Card surface="raised" pad="sm">
              <dl className="space-y-1 text-sm">
                {hit.specs.map((s) => (
                  <div key={s.label} className="flex justify-between">
                    <dt className="text-ink-3">{s.label}</dt>
                    <dd className="text-ink">{s.value}</dd>
                  </div>
                ))}
              </dl>
            </Card>
            <div className="flex gap-3">
              <Button className="flex-1">В корзину</Button>
              <Button variant="outline">Купить в 1 клик</Button>
            </div>
            <p className="text-xs text-ink-3">
              «Нет в наличии» → CTA заменяется на «Узнать о поступлении».
            </p>
          </div>
        </div>
      </Screen>

      {/* 4. Корзина + оформление */}
      <Screen title="4. Корзина и оформление" note="Список позиций + сводка + форма контактов">
        <MiniHeader />
        <div className="grid gap-4 p-4 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            {[hit, order].map((p) => (
              <Card key={p.id} pad="sm" className="flex items-center gap-3">
                <div className="h-16 w-16 shrink-0 rounded-md bg-photo" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink">{p.name}</p>
                  <p className="text-xs text-ink-3">{p.brand}</p>
                </div>
                <span className="text-sm font-semibold text-ink">
                  {p.price.final?.toLocaleString("ru-RU")} ₽
                </span>
              </Card>
            ))}
            <Card surface="raised" pad="md" className="space-y-3">
              <p className="font-semibold text-ink">Контактные данные</p>
              <Field label="Имя" required>
                {(p) => <Input {...p} placeholder="Иван Иванов" />}
              </Field>
              <Field label="Телефон" required>
                {(p) => <Input {...p} placeholder="+7 900 000-00-00" />}
              </Field>
              <Field label="Комментарий">
                {(p) => <Textarea {...p} placeholder="Пожелания к заказу" />}
              </Field>
            </Card>
          </div>
          <Card surface="raised" pad="md" className="h-fit space-y-2">
            <div className="flex justify-between text-sm text-ink-2">
              <span>Товары</span>
              <span>18 480 ₽</span>
            </div>
            <div className="flex justify-between text-sm text-ink-2">
              <span>Доставка</span>
              <span>0 ₽</span>
            </div>
            <div className="flex justify-between text-sm text-ink-3">
              <span>в т.ч. НДС 22%</span>
              <span>3 332 ₽</span>
            </div>
            <div className="mt-2 flex justify-between border-t border-line pt-2 text-base font-bold text-ink">
              <span>Итого</span>
              <span>18 480 ₽</span>
            </div>
            <Button className="mt-2 w-full">Оформить заказ</Button>
          </Card>
        </div>
      </Screen>

      {/* 4b. Успех оформления */}
      <Screen title="4б. Заказ оформлен" note="Экран благодарности">
        <Card pad="none">
          <SuccessState
            title="Заказ №П-2026-0042 оформлен"
            description="Мы свяжемся с вами для подтверждения. Счёт отправлен на email."
            action={<Button>Мои заказы</Button>}
          />
        </Card>
      </Screen>

      {/* 5. Личный кабинет MVP */}
      <Screen title="5. Личный кабинет" note="История заказов (mobile: карточки, пусто-состояние)">
        <MiniHeader />
        <div className="space-y-3 p-4">
          {[
            { n: "П-2026-0042", d: "10.07.2026", s: "Оплачен", sum: "18 480 ₽" },
            { n: "П-2026-0031", d: "02.07.2026", s: "Выполнен", sum: "5 490 ₽" },
          ].map((o) => (
            <Card key={o.n} pad="md" className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-ink">{o.n}</span>
              <span className="text-sm text-ink-3">{o.d}</span>
              <Badge variant="neutral" className="ml-auto">
                {o.s}
              </Badge>
              <span className="text-sm font-semibold text-ink">{o.sum}</span>
            </Card>
          ))}
          <div className="pt-2">
            <p className="mb-2 text-xs text-ink-3">Пустое состояние:</p>
            <Card pad="none">
              <EmptyState
                title="Заказов пока нет"
                description="Оформите первый заказ в каталоге."
                action={<Button variant="outline">В каталог</Button>}
              />
            </Card>
          </div>
        </div>
      </Screen>
      </div>
    </ThemeFrame>
  );
}
