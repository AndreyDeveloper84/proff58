import { SearchIcon } from "lucide-react";
import { ProductCard } from "@/components/product/ProductCard";
import { apiProductToProduct } from "@/lib/adapters";

const API_BASE = process.env.INTERNAL_API_BASE_URL;
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

type ApiProduct = {
  id: number;
  name: string;
  slug: string;
  brand?: string | null;
  category?: { name?: string; slug?: string } | null;
  price?: string | null;
  old_price?: string | null;
  currency?: string | null;
  stock_status?: string | null;
  main_image?: string | null;
  short_description?: string | null;
  attributes?: { name: string; slug: string; unit?: string; value: unknown }[];
};

async function searchProducts(q: string) {
  if (!API_BASE || !q) return [];
  const root = API_BASE.replace(/\/$/, "");
  const res = await fetch(
    `${root}/api/catalog/products/?search=${encodeURIComponent(q)}`,
    { cache: "no-store", headers: SSR_HEADERS },
  );
  if (!res.ok) return [];
  const data = (await res.json()) as { results: ApiProduct[] };
  return (data.results ?? []).map(apiProductToProduct);
}

export default async function SearchPage(props: {
  searchParams: Promise<{ q?: string }>;
}) {
  const searchParams = await props.searchParams;
  const q = searchParams.q ?? "";
  const products = await searchProducts(q);

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="mb-6 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        {q ? (
          <>
            Результаты поиска:{" "}
            <span className="text-accent">&laquo;{q}&raquo;</span>
          </>
        ) : (
          "Поиск"
        )}
      </h1>

      {q && products.length > 0 && (
        <p className="mb-4 text-sm text-ink-3">
          Найдено {products.length}{" "}
          {products.length === 1
            ? "товар"
            : products.length < 5
              ? "товара"
              : "товаров"}
        </p>
      )}

      {q && products.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-line bg-surface p-12 text-center">
          <SearchIcon
            className="h-16 w-16 text-ink-3"
            strokeWidth={1}
          />
          <p className="text-lg text-ink-2">
            По запросу &laquo;{q}&raquo; ничего не найдено
          </p>
          <p className="text-sm text-ink-3">
            Попробуйте изменить запрос или перейдите в каталог
          </p>
          <a
            href="/catalog/perforatory"
            className="mt-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
          >
            Перейти в каталог
          </a>
        </div>
      ) : !q ? (
        <p className="text-ink-3">Введите запрос в строку поиска</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </main>
  );
}
