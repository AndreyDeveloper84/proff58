// Скелетон страницы каталога (§11 loading): fallback Suspense-границы вокруг
// листинга. Раньше лежал в loading.tsx, но фоллбэк сегмента начинал стриминг
// до проверки категории, и notFound() уже не мог выставить 404 — теперь граница
// стоит внутри страницы, ниже проверки раздела (см. app/catalog/[category]/page.tsx).
import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";

export function CatalogSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 xl:px-8" aria-busy aria-hidden>
      {/* breadcrumbs */}
      <div className="mb-3 h-3 w-64 animate-pulse rounded bg-raised" />

      {/* Раскладка повторяет ListingShell: панель подбора слева от самого верха,
          шапка раздела — уже внутри правой колонки. Иначе при появлении данных
          страница перестраивалась на глазах. */}
      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        {/* панель фильтров */}
        <div className="hidden lg:block">
          <div className="h-[560px] animate-pulse rounded-xl border border-line bg-raised" />
        </div>

        <div className="min-w-0">
          {/* шапка раздела */}
          <div className="mb-5 h-[180px] animate-pulse rounded-lg bg-raised lg:h-[280px]" />
          {/* тулбар */}
          <div className="mb-4 h-11 animate-pulse rounded-md bg-raised lg:h-[68px] lg:rounded-xl" />
          <ProductGridSkeleton count={15} />
        </div>
      </div>
    </div>
  );
}
