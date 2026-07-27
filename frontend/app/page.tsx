import { HomeInteractive } from "@/components/home/HomeInteractive";
import { getBestsellers, getCategoryTree } from "@/lib/catalog";
import { resolveStorefront } from "@/lib/site";
import { getSiteTheme } from "@/lib/theme";

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
