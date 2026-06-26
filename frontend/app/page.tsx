import { HomeInteractive } from "@/components/home/HomeInteractive";
import { getBestsellers, getCategoryTree } from "@/lib/catalog";

export default async function Home() {
  const [categories, bestsellers] = await Promise.all([getCategoryTree(), getBestsellers()]);
  return (
    <main>
      <HomeInteractive categories={categories} bestsellers={bestsellers} />
    </main>
  );
}
