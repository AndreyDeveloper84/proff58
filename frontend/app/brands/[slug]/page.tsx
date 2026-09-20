import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { PackageSearch } from "lucide-react";
import { BrandCategoryNav } from "@/components/brand/BrandCategoryNav";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";
import { SearchShell } from "@/components/search/SearchShell";
import { Button } from "@/components/ui/button";
import { getBrandOverview, getBrandProducts, getSearchCount } from "@/lib/catalog";
import type { BrandOverview } from "@/lib/catalog";
import { pluralize } from "@/lib/format";
import { HOME_CONTENT } from "@/lib/home-content";
import { serializeQuery, parseQuery } from "@/lib/url-state";
import type { ListingQuery } from "@/lib/types";

// Страница бренда (UX-07). Плитки «Популярные бренды» раньше вели в текстовый поиск:
// по «Metabo» приезжали чужие запчасти «аналог Metabo», а товары бренда без его имени
// в названии терялись. Здесь выдача точная — по полю бренда, с категориями, сортировкой
// и пагинацией; бренд задан путём и потому переживает любое действие на странице.

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function toQuery(sp: Record<string, string | string[] | undefined>): ListingQuery {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(sp)) {
    if (key === "category" || value == null) continue;
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, v);
  }
  // Фасета «Бренд» на странице бренда нет, а параметр ?brand= из чужой ссылки
  // не должен молча сужать выдачу.
  params.delete("brand");
  return parseQuery(params, first(sp.category));
}

// Курируемый бренд главной известен витрине, даже если в каталоге его пока нет.
function curatedName(slug: string): string | null {
  const hit = Object.entries(HOME_CONTENT.popularBrandSlugs).find(([, s]) => s === slug);
  return hit ? hit[0] : null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const name = curatedName(slug.toLowerCase());
  // Имя из каталога узнаётся только запросом; ради <title> второй раз не ходим.
  return { title: name ? `Товары ${name}` : "Товары бренда" };
}

function Crumbs({ name }: { name: string }) {
  return (
    <nav
      aria-label="Хлебные крошки"
      className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex"
    >
      <Link href="/" className="hover:text-accent">
        Главная
      </Link>
      <span aria-hidden>›</span>
      <Link href="/catalog" className="hover:text-accent">
        Каталог
      </Link>
      <span aria-hidden>›</span>
      <span>{name}</span>
    </nav>
  );
}

// «Бренд известен, но товаров на витрине нет» — отдельное состояние, не 404 и не
// пустая сетка: человек пришёл по плитке главной и должен понять, что делать дальше.
function KnownBrandEmpty({ name }: { name: string }) {
  return (
    <main className="mx-auto w-full max-w-[1680px] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
      <Crumbs name={name} />
      <h1 className="font-display text-2xl font-semibold text-ink lg:text-[30px]">Товары {name}</h1>
      <div className="mt-5 flex flex-col items-center gap-4 rounded-lg border border-line bg-surface p-10 text-center">
        <PackageSearch className="h-14 w-14 text-ink-3" strokeWidth={1.2} aria-hidden />
        <p className="text-lg text-ink">Товаров {name} сейчас нет в каталоге</p>
        <p className="max-w-xl text-sm text-ink-2">
          Бренд нам знаком, но позиций с ним на витрине пока нет. Поиск по названию найдёт
          совместимые изделия и запчасти, если они есть.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link href={`/search?q=${encodeURIComponent(name)}`}>
            <Button variant="accent">Искать «{name}» по каталогу</Button>
          </Link>
          <Link href="/catalog">
            <Button variant="outline">Открыть каталог</Button>
          </Link>
        </div>
      </div>
      <MobileBottomNav active="catalog" />
    </main>
  );
}

// Подсказка под выдачей: поиск по слову находит больше — это совместимые изделия и
// товары, у которых поле бренда не заполнено. В точную выдачу их не подмешиваем.
// Поиск — самый медленный запрос каталога, поэтому считается в своей Suspense-границе.
async function NameMatchesHint({ name, brandTotal }: { name: string; brandTotal: number }) {
  const found = await getSearchCount(name);
  const extra = found == null ? 0 : found - brandTotal;
  if (extra <= 0) return null;
  return (
    <p className="mt-6 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink-2">
      Ещё {extra} {pluralize(extra, "товар упоминает", "товара упоминают", "товаров упоминают")}{" "}
      «{name}» в названии — например, совместимые запчасти и оснастка.{" "}
      <Link
        href={`/search?q=${encodeURIComponent(name)}`}
        className="font-semibold text-accent hover:underline"
      >
        Показать в поиске
      </Link>
    </p>
  );
}

async function BrandProducts({
  pending,
  query,
  overview,
}: {
  pending: ReturnType<typeof getBrandProducts>;
  query: ListingQuery;
  overview: BrandOverview;
}) {
  const { total, products } = await pending;
  return (
    <SearchShell
      listing={{
        category: { title: `Товары ${overview.brand.name}`, intro: "", breadcrumb: [] },
        subcategories: [],
        facets: overview.facets,
        sort: [],
        total,
        page: query.page,
        perPage: query.perPage,
        products,
      }}
      query={query}
      extraParams={{ category: query.category || undefined }}
      resettableParams={["category"]}
      defaultSortLabel="Сначала в наличии"
    />
  );
}

export default async function BrandPage({ params, searchParams }: Props) {
  const [{ slug: rawSlug }, sp] = await Promise.all([params, searchParams]);
  const slug = rawSlug.toLowerCase();
  const query = toQuery(sp);

  // Товары запрашиваем сразу, параллельно с шапкой бренда: последовательно страница
  // стоила бы двух обращений к каталогу подряд. Пустой catch — на случай, когда
  // шапка ответит 404 и до ожидания этого промиса дело не дойдёт.
  const productsPending = getBrandProducts(slug, query);
  productsPending.catch(() => {});

  // Существование бренда выясняем ДО Suspense-границы — по той же причине, что и в
  // каталоге: после первого отданного фоллбэка HTTP-статус уже не изменить, и
  // notFound() из стримящейся части дал бы 404-страницу с кодом 200.
  const overview = await getBrandOverview(slug, query);
  if (!overview) {
    const name = curatedName(slug);
    if (!name) notFound();
    return <KnownBrandEmpty name={name} />;
  }
  if (overview.brandTotal === 0) return <KnownBrandEmpty name={overview.brand.name} />;

  // Ссылки категорий сохраняют сортировку и фильтры, страницу сбрасывают.
  const baseParams = serializeQuery({ ...query, page: 1 });
  const hrefWith = (category?: string) => {
    const usp = new URLSearchParams(baseParams);
    if (category) usp.set("category", category);
    const tail = usp.toString();
    return tail ? `/brands/${slug}?${tail}` : `/brands/${slug}`;
  };
  const name = overview.brand.name;

  return (
    <main className="mx-auto w-full max-w-[1680px] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
      <Crumbs name={name} />
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="font-display text-2xl font-semibold text-ink lg:text-[30px]">
          Товары {name}
        </h1>
        <p className="text-sm text-ink-3">
          {overview.brandTotal}{" "}
          {pluralize(overview.brandTotal, "товар", "товара", "товаров")} в каталоге
        </p>
      </div>

      <BrandCategoryNav
        categories={overview.categories}
        brandTotal={overview.brandTotal}
        allHref={hrefWith()}
        hrefs={Object.fromEntries(overview.categories.map((c) => [c.slug, hrefWith(c.slug)]))}
      />

      {/* key: смена категории/страницы/сортировки заново показывает скелетон, а не
          держит старую сетку до ответа сервера. */}
      <Suspense
        key={JSON.stringify([query.category, query.page, query.sort, query.filters])}
        fallback={
          <div className="mt-5">
            <ProductGridSkeleton view="grid" count={12} />
          </div>
        }
      >
        <BrandProducts pending={productsPending} query={query} overview={overview} />
      </Suspense>

      <Suspense fallback={null}>
        <NameMatchesHint name={name} brandTotal={overview.brandTotal} />
      </Suspense>
      <MobileBottomNav active="catalog" />
    </main>
  );
}
