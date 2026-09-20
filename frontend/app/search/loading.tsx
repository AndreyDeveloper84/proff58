import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";

// Мгновенный отклик на переход в поиск (PERF-01). Страница поиска динамическая, и
// без loading.tsx Next держит прежний экран, пока сервер её не отрендерит: на бою это
// 2–10 секунд без единого признака жизни — так и выглядело «ссылка не нажимается».
// С этим файлом фоллбэк подгружается заранее и показывается сразу по клику.
//
// 404 у поиска не бывает, поэтому ограничение «после фоллбэка HTTP-статус уже не
// изменить» (из-за него у каталога скелетон живёт внутри страницы) здесь не мешает.
export default function SearchLoading() {
  return (
    <main
      aria-busy="true"
      className="mx-auto w-full max-w-[1680px] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7"
    >
      <p role="status" className="sr-only">
        Ищем товары…
      </p>
      <div className="h-8 w-72 max-w-full animate-pulse rounded-md bg-raised" aria-hidden />
      <div className="mt-3 h-11 max-w-2xl animate-pulse rounded-md bg-raised" aria-hidden />
      <div className="mt-5 grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="hidden h-96 animate-pulse rounded-lg bg-raised lg:block" aria-hidden />
        <ProductGridSkeleton view="grid" count={12} />
      </div>
    </main>
  );
}
