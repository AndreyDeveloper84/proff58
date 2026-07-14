import {
  ChevronDown,
  GitCompareArrows,
  Heart,
  LayoutGrid,
  List,
  Menu,
  MessageSquareText,
  Search,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  Truck,
  User,
  Wrench,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

import { PlpCard } from "./PlpCard";
import {
  PLP_ACTIVE_CHIPS,
  PLP_AVAILABILITY,
  PLP_BRANDS,
  PLP_COLLAPSED_GROUPS,
  PLP_PRODUCTS,
  PLP_VOLTAGE,
} from "./mocks";

// hi-fi макет PLP «Шуруповёрты» — пиксель-близко к утверждённым скринам.
// Статическая референс-страница (mock-данные), светлая тема, тёмная шапка/подвал.

function Header() {
  const icons = [
    { icon: GitCompareArrows, label: "Сравнение", count: 0 },
    { icon: Heart, label: "Избранное", count: 3 },
    { icon: ShoppingCart, label: "Корзина", count: 2 },
  ];
  return (
    <header className="bg-header text-header-ink">
      <div className="mx-auto flex max-w-[1280px] items-center gap-4 px-4 py-3">
        {/* Логотип */}
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-brand font-display text-xl font-bold text-white">
            Т
          </span>
          <span className="leading-tight">
            <span className="block font-display text-lg font-bold tracking-wide">ПРОФЕССИОНАЛ</span>
            <span className="block text-[10px] uppercase tracking-widest text-header-ink/60">
              территория инструмента
            </span>
          </span>
        </div>

        {/* Каталог */}
        <button className="ml-2 inline-flex h-11 items-center gap-2 rounded-md bg-brand px-4 font-semibold text-white transition hover:brightness-95">
          <Menu className="h-5 w-5" aria-hidden />
          Каталог
        </button>

        {/* Поиск (светлый инпут на тёмной шапке) */}
        <div className="relative hidden flex-1 md:block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            className="h-11 w-full rounded-md border border-transparent bg-surface pl-10 pr-3 text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            placeholder="Поиск по товарам, брендам, категориям"
          />
        </div>

        {/* Правый блок: телефон + иконки */}
        <div className="ml-auto hidden items-center gap-5 lg:flex">
          <div className="text-right leading-tight">
            <div className="font-display text-base font-bold">8 800 555-27-23</div>
            <div className="text-[11px] text-header-ink/60">Ежедневно с 8:00 до 20:00</div>
          </div>
          {icons.map(({ icon: Icon, label, count }) => (
            <button key={label} className="relative flex flex-col items-center gap-1 text-[11px] text-header-ink/80 hover:text-header-ink">
              <span className="relative">
                <Icon className="h-6 w-6" aria-hidden />
                {count > 0 && (
                  <span className="absolute -right-2 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] font-bold text-white">
                    {count}
                  </span>
                )}
              </span>
              {label}
            </button>
          ))}
          <button className="flex flex-col items-center gap-1 text-[11px] text-header-ink/80 hover:text-header-ink">
            <User className="h-6 w-6" aria-hidden />
            Войти
          </button>
        </div>
      </div>
    </header>
  );
}

function Breadcrumbs() {
  const items = ["Главная", "Каталог", "Электроинструмент", "Шуруповёрты"];
  return (
    <nav aria-label="Хлебные крошки" className="flex flex-wrap items-center gap-2 py-4 text-sm text-ink-3">
      {items.map((c, i) => (
        <span key={c} className="flex items-center gap-2">
          {i < items.length - 1 ? (
            <>
              <span className="cursor-pointer hover:text-ink">{c}</span>
              <span aria-hidden>›</span>
            </>
          ) : (
            <span aria-current="page" className="text-ink-2">
              {c}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}

function CategoryHero() {
  return (
    <section className="relative overflow-hidden rounded-xl border border-line bg-surface">
      {/* Вертикальная тех-линия слева (blueprint-акцент) */}
      <div className="absolute left-6 top-8 bottom-8 hidden w-px bg-brand/40 md:block" aria-hidden>
        <span className="absolute -left-[3px] top-0 h-1.5 w-1.5 rounded-full bg-brand" />
        <span className="absolute -left-[3px] bottom-0 h-1.5 w-1.5 rounded-full bg-brand" />
      </div>
      {/* Blueprint-контур инструмента справа */}
      <Wrench
        className="pointer-events-none absolute -right-6 top-1/2 hidden h-64 w-64 -translate-y-1/2 text-ink/[0.05] lg:block"
        strokeWidth={0.75}
        aria-hidden
      />
      <div className="relative grid gap-4 p-6 md:pl-14">
        <div className="flex items-center gap-4">
          <Wrench className="h-10 w-10 shrink-0 text-ink-2" strokeWidth={1.25} aria-hidden />
          <h1 className="font-display text-3xl font-bold text-ink sm:text-4xl">Шуруповёрты</h1>
          <span className="self-end pb-1 text-sm font-semibold text-brand">126 товаров</span>
        </div>
        <p className="max-w-2xl text-sm leading-relaxed text-ink-2">
          Аккумуляторные и сетевые шуруповёрты для профессионального и бытового использования.
          Официальная гарантия, сервис, быстрая доставка по Пензе и области.
        </p>
      </div>
    </section>
  );
}

function MaxConsult() {
  return (
    <section className="mt-4 flex flex-wrap items-center gap-4 rounded-lg border border-line bg-raised px-5 py-4">
      <MessageSquareText className="h-8 w-8 shrink-0 text-ink-2" strokeWidth={1.5} aria-hidden />
      <div className="min-w-0">
        <p className="font-semibold text-ink">Нужна помощь с выбором?</p>
        <p className="text-sm text-ink-2">
          Консультация в MAX — подберём инструмент под вашу задачу. Отвечает живой специалист.
        </p>
      </div>
      <button className="ml-auto inline-flex h-11 items-center gap-2 rounded-md bg-header px-5 font-semibold text-header-ink transition hover:brightness-110">
        <MessageSquareText className="h-4 w-4" aria-hidden />
        Спросить в MAX
      </button>
    </section>
  );
}

function Chip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-md border border-brand/40 bg-brand/5 px-3 py-2 text-sm text-brand">
      {label}
      <X className="h-3.5 w-3.5 cursor-pointer" aria-hidden />
    </span>
  );
}

function Toolbar() {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-3">
      <button className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-4 text-sm font-semibold text-ink">
        <SlidersHorizontal className="h-4 w-4" aria-hidden />
        Фильтры
        <span className="grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1 text-[11px] font-bold text-white">
          4
        </span>
      </button>
      <button className="text-sm font-medium text-brand hover:underline">Сбросить все</button>
      <div className="hidden flex-wrap gap-2 xl:flex">
        {PLP_ACTIVE_CHIPS.map((c) => (
          <Chip key={c} label={c} />
        ))}
      </div>
      <div className="ml-auto flex items-center gap-3">
        <button className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-4 text-sm text-ink-2">
          Сначала в наличии
          <ChevronDown className="h-4 w-4" aria-hidden />
        </button>
        <div className="hidden items-center rounded-md border border-line sm:flex">
          <span className="grid h-11 w-11 place-items-center rounded-l-md bg-brand text-white">
            <LayoutGrid className="h-4 w-4" aria-hidden />
          </span>
          <span className="grid h-11 w-11 place-items-center text-ink-3">
            <List className="h-4 w-4" aria-hidden />
          </span>
        </div>
      </div>
    </div>
  );
}

function FacetGroup({
  title,
  children,
  collapsed,
}: {
  title: string;
  children?: React.ReactNode;
  collapsed?: boolean;
}) {
  return (
    <div className="border-t border-line py-4 first:border-t-0 first:pt-0">
      <button className="flex w-full items-center justify-between text-sm font-semibold text-ink">
        {title}
        <ChevronDown
          className={cn("h-4 w-4 text-ink-3 transition", collapsed && "-rotate-90")}
          aria-hidden
        />
      </button>
      {!collapsed && children && <div className="mt-3">{children}</div>}
    </div>
  );
}

function Check({
  label,
  count,
  checked,
}: {
  label: string;
  count?: number;
  checked?: boolean;
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm text-ink-2 hover:text-ink sm:min-h-9">
      <span
        className={cn(
          "grid h-5 w-5 shrink-0 place-items-center rounded border",
          checked ? "border-brand bg-brand text-white" : "border-line",
        )}
      >
        {checked && (
          <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none" aria-hidden>
            <path d="M2 6.5 4.5 9 10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      <span className="flex-1">{label}</span>
      {count != null && <span className="text-ink-3">{count}</span>}
    </label>
  );
}

function Sidebar() {
  return (
    <aside className="hidden w-[280px] shrink-0 lg:block">
      <div className="rounded-lg border border-line bg-surface p-4">
        <FacetGroup title="Наличие">
          <div>
            {PLP_AVAILABILITY.map((a) => (
              <Check key={a.label} label={a.label} count={a.count} checked={a.checked} />
            ))}
          </div>
        </FacetGroup>

        <FacetGroup title="Цена, ₽">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <input
                defaultValue="от 2 990"
                className="h-10 w-full rounded-md border border-line bg-surface px-3 text-sm text-ink"
              />
              <input
                defaultValue="до 39 990"
                className="h-10 w-full rounded-md border border-line bg-surface px-3 text-sm text-ink"
              />
            </div>
            <div className="relative h-1.5 rounded-full bg-line">
              <span className="absolute inset-y-0 left-[8%] right-[15%] rounded-full bg-brand" />
              <span className="absolute -top-1 left-[8%] h-3.5 w-3.5 -translate-x-1/2 rounded-full border-2 border-surface bg-brand" />
              <span className="absolute -top-1 right-[15%] h-3.5 w-3.5 translate-x-1/2 rounded-full border-2 border-surface bg-brand" />
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-ink-3">
              <span>до 5 000</span>
              <span>5 000 – 10 000</span>
              <span>10 000 – 20 000</span>
              <span>от 20 000</span>
            </div>
          </div>
        </FacetGroup>

        <FacetGroup title="Бренд">
          <div className="space-y-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" aria-hidden />
              <input
                placeholder="Поиск бренда"
                className="h-10 w-full rounded-md border border-line bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-ink-3"
              />
            </div>
            <div>
              {PLP_BRANDS.map((b) => (
                <Check key={b.label} label={b.label} count={b.count} checked={b.checked} />
              ))}
            </div>
            <button className="text-sm font-medium text-brand hover:underline">Показать ещё (12)</button>
          </div>
        </FacetGroup>

        <FacetGroup title="Напряжение, В">
          <div>
            {PLP_VOLTAGE.map((v) => (
              <Check key={v.label} label={v.label} count={v.count} checked={v.checked} />
            ))}
          </div>
        </FacetGroup>

        {PLP_COLLAPSED_GROUPS.map((g) => (
          <FacetGroup key={g} title={g} collapsed />
        ))}
      </div>
    </aside>
  );
}

function Pagination() {
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-1.5 text-sm">
        <span className="grid h-9 min-w-9 place-items-center rounded-md bg-brand px-2 font-semibold text-white">1</span>
        {["2", "3", "4", "5", "…", "52"].map((n) => (
          <span key={n} className="grid h-9 min-w-9 cursor-pointer place-items-center rounded-md px-2 text-ink-2 hover:bg-raised">
            {n}
          </span>
        ))}
      </div>
      <div className="flex items-center gap-2 text-sm text-ink-3">
        Показывать по:
        <button className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-ink-2">
          24 <ChevronDown className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}

const TRUST = [
  { icon: ShieldCheck, title: "Оригинальный инструмент", sub: "Только официальные поставки" },
  { icon: ShieldCheck, title: "Гарантия до 5 лет", sub: "Сервис в 120+ городах России" },
  { icon: GitCompareArrows, title: "Возврат 14 дней", sub: "Без лишних вопросов" },
  { icon: Truck, title: "Быстрая доставка", sub: "По всей России от 1 дня" },
];

function TrustBar() {
  return (
    <section className="mt-8 border-t border-line bg-raised">
      <div className="mx-auto grid max-w-[1280px] grid-cols-1 gap-4 px-4 py-6 sm:grid-cols-2 lg:grid-cols-4">
        {TRUST.map(({ icon: Icon, title, sub }) => (
          <div key={title} className="flex items-center gap-3">
            <Icon className="h-7 w-7 shrink-0 text-brand" strokeWidth={1.5} aria-hidden />
            <div className="leading-tight">
              <div className="text-sm font-semibold text-ink">{title}</div>
              <div className="text-xs text-ink-3">{sub}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function PlpPage() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Header />
      <main className="mx-auto max-w-[1280px] px-4 pb-4">
        <Breadcrumbs />
        <CategoryHero />
        <MaxConsult />
        <Toolbar />
        <div className="mt-4 flex gap-6">
          <Sidebar />
          <div className="min-w-0 flex-1">
            <p className="mb-3 text-sm text-ink-2">Найдено 1 248 товаров</p>
            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-3">
              {PLP_PRODUCTS.map((p) => (
                <PlpCard key={p.id} p={p} />
              ))}
            </div>
            <div className="mt-6 flex justify-center">
              <button className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-6 text-sm font-medium text-ink-2 hover:bg-raised">
                Показать ещё 24 товара
                <ChevronDown className="h-4 w-4" aria-hidden />
              </button>
            </div>
            <Pagination />
          </div>
        </div>
      </main>
      <TrustBar />
    </div>
  );
}
