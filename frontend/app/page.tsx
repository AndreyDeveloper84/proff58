import { HomeInteractive } from "@/components/home/HomeInteractive";
import { getBestsellers } from "@/lib/catalog";

// Хиты продаж и тема берутся из API в рантайме. Без этого Next 16 пререндерит
// главную на этапе build, где INTERNAL_API_BASE_URL ещё нет (переменная приходит
// только в runtime, docker-compose.prod.yml) — и пустые списки «цементируются»
// в статике до следующей сборки. cache:"no-store" в fetch сам по себе роут
// динамическим больше не делает (изменение Next 15→16), поэтому нужен явный
// force-dynamic — как на /catalog.
export const dynamic = "force-dynamic";

export default async function Home() {
  const bestsellers = await getBestsellers();
  return (
    <main className="bg-surface">
      <HomeInteractive bestsellers={bestsellers} />
    </main>
  );
}
