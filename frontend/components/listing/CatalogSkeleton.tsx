// Скелетон страницы каталога (§11 loading): показывается во время SSR-навигации
// сегмента. Skeleton для контента (hero/тулбар/сайдбар/карточки), без спиннера.
import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";

export default function CatalogLoading() {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6" aria-busy aria-hidden>
      {/* breadcrumbs */}
      <div className="mb-3 h-3 w-64 animate-pulse rounded bg-raised" />
      {/* hero */}
      <div className="mb-6 h-40 animate-pulse rounded-xl border border-line bg-raised" />
      {/* consult banner */}
      <div className="mb-6 h-20 animate-pulse rounded-lg border border-line bg-raised" />

      {/* toolbar */}
      <div className="mb-4 flex gap-3">
        <div className="h-11 w-28 animate-pulse rounded-md bg-raised" />
        <div className="h-11 w-24 animate-pulse rounded-md bg-raised" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        {/* sidebar */}
        <div className="hidden lg:block">
          <div className="h-[520px] animate-pulse rounded-lg border border-line bg-raised" />
        </div>
        {/* grid */}
        <div className="min-w-0">
          <div className="mb-3 h-4 w-40 animate-pulse rounded bg-raised" />
          <ProductGridSkeleton count={15} />
        </div>
      </div>
    </div>
  );
}
