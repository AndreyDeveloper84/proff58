import { HomeInteractive } from "@/components/home/HomeInteractive";
import { getBestsellers, getCategoryTree } from "@/lib/catalog";
import { resolveStorefront } from "@/lib/site";
import { getSiteTheme } from "@/lib/theme";

// Категории, хиты продаж и тема берутся из API в рантайме. Без этого Next 16
// пререндерит главную на этапе build, где INTERNAL_API_BASE_URL ещё нет
// (переменная приходит только в runtime, docker-compose.prod.yml) — и пустые
// списки «цементируются» в статике до следующей сборки. cache:"no-store"
// в fetch сам по себе роут динамическим больше не делает (изменение Next 15→16),
// поэтому нужен явный force-dynamic — как на /catalog.
export const dynamic = "force-dynamic";

export default async function Home() {
  const [categories, bestsellers, theme] = await Promise.all([
    getCategoryTree(),
    getBestsellers(),
    getSiteTheme(),
  ]);
  return (
    <main className="bg-surface">
      <HomeInteractive
        categories={categories}
        bestsellers={bestsellers}
        storefront={resolveStorefront(theme)}
      />
    </main>
  );
}
