import {
  ArrowRight,
  BadgeCheck,
  CircleGauge,
  Hammer,
  MessageSquareText,
  PackageCheck,
  PlugZap,
  RotateCcw,
  ShieldCheck,
  Truck,
  Wrench,
  Zap,
} from "lucide-react";
import { Collapsible } from "./Collapsible";
import { SITE } from "@/lib/site";
import { pickUseCases } from "@/lib/pdp-usecases";
import type { ProductDetail, ProductSpec } from "@/lib/types";

type SpecGroup = {
  title: string;
  icon: typeof Zap;
  specs: ProductSpec[];
};

const KEY_SPEC_PATTERNS = [
  /мощност/i,
  /энерги.*удар/i,
  /тип.*патрон|патрон/i,
  /режим/i,
  /напряжен|аккумулятор/i,
  /диаметр/i,
  /производительност/i,
  /давлен/i,
];

const GROUPS = [
  {
    title: "Производительность",
    icon: CircleGauge,
    test:
      /мощност|энерги|частот|оборот|скорост|производительност|давлен|расход|усили|диаметр|глубин|крутящ/i,
  },
  {
    title: "Оснастка",
    icon: Wrench,
    test: /патрон|оснаст|креплен|насад|режим|реверс|муфт|комплект|кейс|диск|бур|сверл/i,
  },
  {
    title: "Питание и корпус",
    icon: PlugZap,
    test: /питан|напряжен|аккумулятор|ёмкост|емкост|кабел|вес|размер|габарит|материал|корпус|длин|ширин|высот/i,
  },
] as const;

export function selectKeySpecs(specs: ProductSpec[], limit = 4): ProductSpec[] {
  const selected: ProductSpec[] = [];
  const used = new Set<number>();

  for (const pattern of KEY_SPEC_PATTERNS) {
    const index = specs.findIndex((spec, i) => !used.has(i) && pattern.test(spec.label));
    if (index === -1) continue;
    selected.push(specs[index]);
    used.add(index);
    if (selected.length === limit) return selected;
  }

  for (let i = 0; i < specs.length && selected.length < limit; i += 1) {
    if (used.has(i) || /тип инструмента/i.test(specs[i].label)) continue;
    selected.push(specs[i]);
  }
  return selected;
}

/**
 * Есть ли что показывать в техническом паспорте.
 *
 * Тип инструмента — служебная строка разбора каталога, а не характеристика: у
 * 12 тысяч товаров он единственный, и паспорт из одной строки «Тип инструмента:
 * Газонокосилки» читался как обрезанная таблица. Нет чего показывать — нет и
 * раздела.
 */
export function hasPassportSpecs(specs: ProductSpec[]): boolean {
  return specs.some((spec) => !/тип инструмента/i.test(spec.label));
}

export function groupProductSpecs(specs: ProductSpec[]): SpecGroup[] {
  const buckets = GROUPS.map((group) => ({ ...group, specs: [] as ProductSpec[] }));
  const other: ProductSpec[] = [];

  for (const spec of specs) {
    const bucket = buckets.find((group) => group.test.test(spec.label));
    (bucket?.specs ?? other).push(spec);
  }

  return [
    ...buckets.map(({ title, icon, specs: groupedSpecs }) => ({
      title,
      icon,
      specs: groupedSpecs,
    })),
    { title: "Дополнительно", icon: PackageCheck, specs: other },
  ].filter((group) => group.specs.length > 0);
}

const METRIC_ICONS = [Zap, Hammer, Wrench, CircleGauge];

function MetricCards({ specs }: { specs: ProductSpec[] }) {
  const metrics = selectKeySpecs(specs);
  if (!metrics.length) return null;

  return (
    <section aria-labelledby="key-metrics-title">
      <h2 id="key-metrics-title" className="font-display text-xl font-semibold text-ink">
        Главное в работе
      </h2>
      {/* Две колонки уже на телефоне: в один столбец четыре карточки занимали
          пол-экрана, и до технического паспорта приходилось долго скроллить. */}
      <div className="mt-3 grid grid-cols-2 gap-2.5 sm:gap-3 xl:grid-cols-4">
        {metrics.map((spec, index) => {
          const Icon = METRIC_ICONS[index % METRIC_ICONS.length];
          return (
            <div
              key={`${spec.label}-${spec.value}`}
              className="flex min-h-20 items-center gap-2.5 rounded-lg border border-line bg-surface p-3 sm:min-h-24 sm:gap-3"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-accent text-accent-ink shadow-sm sm:h-12 sm:w-12">
                <Icon className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />
              </span>
              <span className="min-w-0">
                <strong className="block break-words font-display text-base font-semibold leading-tight text-ink sm:text-lg">
                  {spec.value}
                </strong>
                <span className="mt-0.5 block text-xs leading-snug text-ink-3">{spec.label}</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SpecGroups({ specs }: { specs: ProductSpec[] }) {
  const groups = groupProductSpecs(specs);
  const content = (
    <div className="overflow-hidden rounded-lg border border-line bg-surface px-3 sm:px-4">
      {groups.map((group) => {
        const Icon = group.icon;
        return (
          <section key={group.title} className="border-b border-line py-4 last:border-b-0">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Icon className="h-4 w-4 text-accent" aria-hidden />
              {group.title}
            </h3>
            <dl className="mt-3 divide-y divide-line">
              {group.specs.map((spec, index) => (
                <div
                  key={`${spec.label}-${index}`}
                  className="grid gap-0.5 py-2 text-sm first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,1fr)_minmax(150px,.75fr)] sm:gap-4"
                >
                  <dt className="text-ink-3">{spec.label}</dt>
                  <dd className="font-medium text-ink-2 sm:text-right">{spec.value}</dd>
                </div>
              ))}
            </dl>
          </section>
        );
      })}
    </div>
  );

  return (
    <section id="characteristics" className="scroll-mt-28" aria-labelledby="passport-title">
      <h2 id="passport-title" className="mb-3 font-display text-xl font-semibold text-ink">
        Технический паспорт
      </h2>
      {specs.length > 14 ? (
        <Collapsible collapsedHeight={720} moreLabel="Все характеристики">
          {content}
        </Collapsible>
      ) : (
        content
      )}
    </section>
  );
}

const USE_CASE_ICONS = [BadgeCheck, Wrench, CircleGauge];

function ExpertPanel({ specs, wide = false }: { specs: ProductSpec[]; wide?: boolean }) {
  // Сценарии зависят от типа инструмента: у перфоратора это бурение и штробление,
  // у мойки — фасад и автомобиль. Для типа без своей записи остаётся честный
  // запасной набор про помощь магазина — выдумывать применение нельзя.
  const { cases, isGeneric } = pickUseCases(specs);
  const items = cases.map((useCase, index) => ({
    ...useCase,
    icon: USE_CASE_ICONS[index % USE_CASE_ICONS.length],
  }));

  return (
    <aside className="overflow-hidden rounded-lg bg-expert text-expert-ink shadow-md">
      <div className="p-4 sm:p-5">
        <h2 className="font-display text-2xl font-semibold">
          {isGeneric ? "Поможем с выбором" : "Подойдёт для"}
        </h2>
        {/* Без паспорта рядом панель занимает всю ширину — сценарии тогда идут
            в ряд, иначе три строки текста растягиваются на весь экран. */}
        <div
          className={
            wide
              ? "mt-4 grid gap-4 sm:grid-cols-3"
              : "mt-4 divide-y divide-white/10"
          }
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.title}
                className={
                  wide ? "flex gap-3" : "flex gap-3 border-t border-white/10 py-4 first:border-t-0 first:pt-0"
                }
              >
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-md border border-white/15 text-accent">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <span>
                  <strong className="block text-sm font-semibold">{item.title}</strong>
                  <span className="mt-1 block text-xs leading-relaxed text-white/70">
                    {item.text}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {/* Телефон, а не мессенджер: адрес бота MAX приходит с сервера и может быть
          пуст, а битую ссылку в signature-панели показывать нельзя. Звонок —
          то, что работает всегда. */}
      <a
        href={SITE.phone.href}
        data-event="pdp_expert_help"
        className="group m-3 mt-0 flex min-h-16 items-center gap-3 rounded-md bg-surface p-3 text-ink transition hover:bg-raised sm:m-4 sm:mt-0"
      >
        <MessageSquareText className="h-6 w-6 shrink-0 text-accent" aria-hidden />
        <span className="min-w-0 flex-1">
          <strong className="block text-sm font-semibold">Задать вопрос специалисту</strong>
          <span className="mt-0.5 block text-xs text-ink-3">{SITE.phone.display}</span>
        </span>
        <ArrowRight className="h-5 w-5 text-accent transition-transform group-hover:translate-x-0.5" aria-hidden />
      </a>
    </aside>
  );
}

function PurchaseConfidence() {
  const items = [
    { icon: Truck, title: "Быстрая доставка", text: "По Пензе и области" },
    { icon: ShieldCheck, title: "Официальная гарантия", text: "На ассортимент магазина" },
    { icon: RotateCcw, title: "Возврат за 14 дней", text: "Если товар не подошёл" },
  ];

  return (
    <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="confidence-title">
      <h2 id="confidence-title" className="font-display text-lg font-semibold text-ink">
        Покупка без сюрпризов
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.title} className="flex items-start gap-2.5">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
              <span>
                <strong className="block text-sm font-semibold text-ink">{item.title}</strong>
                <span className="mt-0.5 block text-xs text-ink-3">{item.text}</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function ProductDetailsShowcase({ product }: { product: ProductDetail }) {
  if (!product.specs.length && !product.description) return null;

  const hasPassport = hasPassportSpecs(product.specs);

  return (
    <div className="space-y-5">
      {hasPassport && <MetricCards specs={product.specs} />}

      {hasPassport ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.18fr)_minmax(320px,.82fr)]">
          <SpecGroups specs={product.specs} />
          <div className="lg:sticky lg:top-28">
            <ExpertPanel specs={product.specs} />
          </div>
        </div>
      ) : (
        <ExpertPanel specs={product.specs} wide />
      )}

      <PurchaseConfidence />

      {product.description && (
        <section id="description" className="scroll-mt-28 rounded-lg border border-line bg-surface p-4 sm:p-5">
          <h2 className="mb-3 font-display text-xl font-semibold text-ink">Описание</h2>
          {product.description.length > 600 ? (
            <Collapsible collapsedHeight={240}>
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink-2">
                {product.description}
              </p>
            </Collapsible>
          ) : (
            <p className="whitespace-pre-line text-sm leading-relaxed text-ink-2">
              {product.description}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
