import Link from "next/link";
import {
  Anvil,
  Archive,
  ArrowRight,
  BatteryCharging,
  Boxes,
  CarFront,
  Drill,
  Flame,
  Gauge,
  Hammer,
  HardHat,
  Leaf,
  Lightbulb,
  Nut,
  PackageOpen,
  Ruler,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { ConsultBanner } from "@/components/listing/ConsultBanner";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { SearchBar } from "@/components/layout/SearchBar";
import type { CategoryNode } from "@/lib/catalog";
import { cn } from "@/lib/utils";

// Категории берём из API в рантайме (slug'и из БД), без редиректа.
export const dynamic = "force-dynamic";

async function getCategories(): Promise<CategoryNode[] | null> {
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) {
    // Локально/без API оставляем только существующую fixture-категорию:
    // не рисуем каноническое дерево с неработающими ссылками.
    return [
      {
        id: 0,
        name: "Перфораторы (демо)",
        slug: "perforatory",
        sort_order: 0,
        children: [],
      },
    ];
  }
  try {
    const response = await fetch(`${base.replace(/\/$/, "")}/api/catalog/categories/`, {
      cache: "no-store",
      headers: { "X-Forwarded-Proto": "https" },
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return null;
    const tree = (await response.json()) as CategoryNode[];
    return Array.isArray(tree) ? tree : null;
  } catch {
    return null;
  }
}

type CategoryVisual = {
  icon: LucideIcon;
  accent: string;
  surface: string;
};

const DEFAULT_VISUAL: CategoryVisual = {
  icon: Boxes,
  accent: "text-accent",
  surface: "bg-accent/[0.07]",
};

// В API пока нет category.image. Иконка — только оформление реального узла;
// она определяется по имени, но название, ссылка и подкатегории всегда серверные.
function categoryVisual(name: string): CategoryVisual {
  const value = name.toLocaleLowerCase("ru-RU");
  const rules: Array<[RegExp, CategoryVisual]> = [
    [
      /оснаст|расход/,
      { icon: PackageOpen, accent: "text-amber-600", surface: "bg-amber-50" },
    ],
    [/электроинструмент|перфоратор/, { ...DEFAULT_VISUAL, icon: Drill }],
    [/ручн/, { icon: Wrench, accent: "text-sky-700", surface: "bg-sky-50" }],
    [/авто|гараж/, { icon: CarFront, accent: "text-slate-700", surface: "bg-slate-100" }],
    [/измер/, { icon: Ruler, accent: "text-amber-600", surface: "bg-amber-50" }],
    [/крепёж|метиз/, { icon: Nut, accent: "text-slate-600", surface: "bg-slate-100" }],
    [/электрик|освещ/, { icon: Lightbulb, accent: "text-amber-500", surface: "bg-amber-50" }],
    [/спецодеж|сиз/, { icon: HardHat, accent: "text-orange-600", surface: "bg-orange-50" }],
    [/садов/, { icon: Leaf, accent: "text-accent", surface: "bg-accent/[0.07]" }],
    [
      /силов|пневм|компресс/,
      { icon: Gauge, accent: "text-sky-700", surface: "bg-sky-50" },
    ],
    [/свароч/, { icon: Flame, accent: "text-orange-600", surface: "bg-orange-50" }],
    [/хранен|организац/, { icon: Archive, accent: "text-slate-700", surface: "bg-slate-100" }],
    [/строитель|отделоч/, { icon: Hammer, accent: "text-sky-700", surface: "bg-sky-50" }],
    [
      /запчаст|аккумулятор|комплектующ/,
      { icon: BatteryCharging, accent: "text-accent", surface: "bg-accent/[0.07]" },
    ],
    [/сварк|кузнеч/, { icon: Anvil, accent: "text-orange-600", surface: "bg-orange-50" }],
  ];

  return rules.find(([pattern]) => pattern.test(value))?.[1] ?? DEFAULT_VISUAL;
}

function CategoryCard({
  category,
  featured,
}: {
  category: CategoryNode;
  featured: boolean;
}) {
  const visual = categoryVisual(category.name);
  const Icon = visual.icon;
  const children = category.children.slice(0, 3);

  return (
    <Link
      href={`/catalog/${category.slug}`}
      className={cn(
        "group relative flex min-h-[158px] overflow-hidden rounded-lg border border-line bg-surface p-4 transition duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-md sm:min-h-[176px]",
        featured ? "lg:min-h-[188px] lg:p-5" : "lg:min-h-[132px] lg:p-4",
      )}
    >
      <div
        className={cn(
          "absolute -right-5 -top-5 grid h-28 w-28 place-items-center rounded-full transition duration-300 group-hover:scale-105 sm:h-32 sm:w-32",
          visual.surface,
          featured ? "lg:-right-4 lg:-top-4 lg:h-36 lg:w-36" : "lg:h-28 lg:w-28",
        )}
        aria-hidden
      >
        <Icon
          className={cn(
            "h-14 w-14 stroke-[1.35] sm:h-16 sm:w-16",
            visual.accent,
            featured ? "lg:h-[76px] lg:w-[76px]" : "lg:h-14 lg:w-14",
          )}
        />
      </div>

      <div className="relative z-10 flex min-w-0 max-w-[78%] flex-1 flex-col justify-end sm:max-w-[72%]">
        <h2
          className={cn(
            "text-sm font-semibold leading-snug text-ink transition group-hover:text-accent",
            featured && "lg:text-base",
          )}
        >
          {category.name}
        </h2>

        {children.length > 0 && (
          <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-ink-3">
            {children.map((child) => child.name).join(", ")}
          </p>
        )}

        <span className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
          Смотреть
          <ArrowRight
            className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1"
            aria-hidden
          />
        </span>
      </div>
    </Link>
  );
}

export async function generateMetadata() {
  return { title: "Каталог — Профессионал" };
}

export default async function CatalogIndexPage() {
  const categories = await getCategories();

  return (
    <main className="min-h-[70vh] bg-canvas pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
        <nav
          aria-label="Хлебные крошки"
          className="mb-3 flex items-center gap-2 text-xs text-ink-3"
        >
          <Link href="/" className="transition hover:text-accent">
            Главная
          </Link>
          <span aria-hidden>›</span>
          <span className="text-ink-2">Каталог</span>
        </nav>

        <h1 className="font-display text-3xl font-semibold text-ink lg:text-[34px]">
          Каталог товаров
        </h1>

        <SearchBar
          className="mt-4 max-w-none [&_form]:h-11 lg:mt-5"
          placeholder="Поиск по каталогу"
        />

        {categories == null ? (
          <section className="mt-5 grid min-h-64 place-items-center rounded-lg border border-line bg-surface p-8 text-center">
            <div>
              <PackageOpen className="mx-auto h-12 w-12 text-ink-3" aria-hidden />
              <h2 className="mt-4 text-lg font-semibold text-ink">
                Каталог временно недоступен
              </h2>
              <p className="mt-1 text-sm text-ink-2">Обновите страницу немного позже.</p>
            </div>
          </section>
        ) : categories.length === 0 ? (
          <section className="mt-5 grid min-h-64 place-items-center rounded-lg border border-line bg-surface p-8 text-center">
            <div>
              <PackageOpen className="mx-auto h-12 w-12 text-ink-3" aria-hidden />
              <h2 className="mt-4 text-lg font-semibold text-ink">Категории пока не заполнены</h2>
              <p className="mt-1 text-sm text-ink-2">
                После публикации разделов они появятся здесь автоматически.
              </p>
            </div>
          </section>
        ) : (
          <>
            <section
              aria-label="Категории товаров"
              className="mt-4 grid grid-cols-2 gap-3 lg:mt-5 lg:grid-cols-4"
            >
              {categories.map((category, index) => (
                <CategoryCard
                  key={category.id}
                  category={category}
                  featured={index < 4}
                />
              ))}
            </section>

            <ConsultBanner className="mt-5 bg-surface lg:px-5 lg:py-4" />
          </>
        )}
      </div>

      <MobileBottomNav active="catalog" />
    </main>
  );
}
