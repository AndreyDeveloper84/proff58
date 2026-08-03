import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  PackageOpen,
} from "lucide-react";
import { WhyBuyStrip } from "@/components/home/HomeBottom";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { getCategoryTreeOrNull, type CategoryNode } from "@/lib/catalog";
import { categoryPhoto } from "@/lib/category-artwork";
import { cn } from "@/lib/utils";

// Категории берём из API в рантайме (slug'и из БД), без редиректа. Данные — через
// lib/catalog.ts (единственная точка интеграции), fetch тут не дублируем.
export const dynamic = "force-dynamic";

//: Сколько первых разделов показывать крупно — ровно один ряд сетки на десктопе.
const FEATURED_CATEGORIES = 4;

function CategoryCard({
  category,
  featured = false,
}: {
  category: CategoryNode;
  // Крупная карточка: фото сверху во всю ширину, а не маленькое сбоку.
  // Первый ряд разделов подаётся заметнее — с него начинают почти все.
  featured?: boolean;
}) {
  const artwork = categoryPhoto(category.name);
  const children = category.children.slice(0, 3);

  return (
    <Link
      href={`/catalog/${category.slug}`}
      className={cn(
        "group relative flex min-h-[132px] overflow-hidden rounded-md border border-line bg-surface p-3 transition duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-md",
        featured ? "lg:min-h-[184px] lg:p-4" : "lg:min-h-[128px]",
      )}
    >
      <div
        className={cn(
          "pointer-events-none absolute inset-x-2 top-1 h-[78px] transition duration-300 group-hover:scale-[1.03]",
          featured
            ? "lg:inset-x-3 lg:top-1 lg:h-[124px]"
            : "lg:inset-y-2 lg:left-2 lg:right-auto lg:top-2 lg:h-auto lg:w-[108px]",
        )}
        aria-hidden
      >
        {artwork ? (
          <Image
            src={artwork}
            alt=""
            fill
            loading="eager"
            unoptimized
            sizes={featured ? "(max-width: 1023px) 40vw, 280px" : "(max-width: 1023px) 40vw, 108px"}
            className="object-contain"
          />
        ) : (
          <span className="mx-auto grid h-full aspect-square place-items-center rounded-full bg-accent/[0.07] text-accent">
            <Boxes className="h-10 w-10" strokeWidth={1.4} />
          </span>
        )}
      </div>

      <div
        className={cn(
          "relative z-10 mt-auto flex min-w-0 flex-1 flex-col justify-end pt-[78px]",
          featured ? "lg:pt-[124px]" : "lg:ml-[116px] lg:my-auto lg:justify-center lg:pt-0",
        )}
      >
        <h2
          className={cn(
            "line-clamp-3 pr-4 text-[11px] font-semibold leading-[1.25] text-ink transition group-hover:text-accent sm:text-sm lg:line-clamp-2",
            featured ? "lg:text-[14px]" : "lg:text-[13px]",
          )}
        >
          {category.name}
        </h2>

        {children.length > 0 && (
          <p className="mt-1 hidden line-clamp-2 text-[10px] leading-[1.35] text-ink-3 lg:block">
            {children.map((child) => child.name).join(", ")}
          </p>
        )}
      </div>

      <ArrowRight
        className="absolute bottom-3 right-3 h-4 w-4 text-accent transition-transform group-hover:translate-x-1"
        aria-hidden
      />
    </Link>
  );
}

// Суффикс «— Профессионал» дописывает шаблон title из app/layout.tsx.
export async function generateMetadata() {
  return { title: "Каталог" };
}

export default async function CatalogIndexPage() {
  const categories = await getCategoryTreeOrNull();

  return (
    <main className="min-h-[70vh] bg-surface pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1680px] px-4 py-5 sm:px-6 xl:px-8">
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

        <h1 className="font-display text-[28px] font-semibold text-ink lg:text-[32px]">
          Каталог товаров
        </h1>

        <SearchBar
          className="mt-3 max-w-none [&_input]:h-10 lg:mt-3"
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
            {/* Первый ряд — крупными карточками, отдельной сеткой строго по
                четыре. В общей сетке этого не сделать: с 2xl в ней пять колонок,
                и четвёрка вставала бы неровно, оставляя рядом чужую мелкую
                карточку. Ниже — остальные разделы во всю ширину. */}
            <section aria-label="Категории товаров" className="mt-3">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4 lg:gap-2.5">
                {categories.slice(0, FEATURED_CATEGORIES).map((category) => (
                  <CategoryCard key={category.id} category={category} featured />
                ))}
              </div>

              {categories.length > FEATURED_CATEGORIES && (
                <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3 lg:mt-2.5 lg:grid-cols-4 lg:gap-2.5 2xl:grid-cols-5">
                  {categories.slice(FEATURED_CATEGORIES).map((category) => (
                    <CategoryCard key={category.id} category={category} />
                  ))}
                </div>
              )}
            </section>

            <div className="mt-3 hidden lg:block">
              <WhyBuyStrip />
            </div>
          </>
        )}
      </div>

      <MobileBottomNav active="catalog" />
    </main>
  );
}
