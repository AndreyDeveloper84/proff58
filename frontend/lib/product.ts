// Слой данных PDP — fetch одного товара по slug.
// Эндпоинт: GET /api/catalog/products/{slug}/
// 404 → null → notFound() в page.tsx; остальные ошибки пробрасываются → error.tsx.

import type { StockState, BadgeKind, ProductSpec } from "./types";

// --- API response shape ---

export type ApiProductImage = {
  url: string;
  alt?: string;
  is_main?: boolean;
};

type ApiBreadcrumb = { name: string; slug: string };

type ApiCategory = { name: string; slug: string };

type ApiAttribute = { name: string; slug: string; unit?: string; value: unknown };

type ApiProductDetail = {
  id: number;
  name: string;
  slug: string;
  brand?: string | null;
  category?: ApiCategory | null;
  price?: string | null;
  old_price?: string | null;
  currency?: string | null;
  price_type?: string | null;
  stock_status?: string | null;
  main_image?: string | null;
  short_description?: string | null;
  description?: string | null;
  meta_title?: string | null;
  meta_description?: string | null;
  images?: ApiProductImage[];
  attributes?: ApiAttribute[];
  breadcrumb?: ApiBreadcrumb[];
};

// --- UI types ---

export type ProductDetailImage = {
  url: string;
  alt: string;
  isMain: boolean;
};

export type ProductDetail = {
  id: number;
  name: string;
  slug: string;
  brand: string;
  category: { name: string; slug: string } | null;
  price: { final?: number; old?: number; discountPct?: number; currency: "RUB" };
  stock: StockState;
  mainImage?: string;
  shortDescription?: string;
  description?: string;
  metaTitle?: string;
  metaDescription?: string;
  images: ProductDetailImage[];
  specs: ProductSpec[];
  badges: BadgeKind[];
  breadcrumb: { name: string; slug: string }[];
};

// --- helpers ---

const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

function num(v: unknown): number | undefined {
  if (v == null || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function mapStock(s?: string | null): StockState {
  if (s === "in_stock") return "in";
  if (s === "on_order") return "order";
  return "out";
}

function formatSpecValue(value: unknown, unit?: string): string {
  if (value == null || value === "") return "";
  let s: string;
  if (typeof value === "boolean") s = value ? "Да" : "Нет";
  else if (typeof value === "number") s = String(value).replace(".", ",");
  else s = String(value);
  const u = (unit ?? "").trim();
  if (u && !s.includes(u)) s = `${s} ${u}`;
  return s.trim();
}

function mapImages(
  images?: ApiProductImage[],
  mainImage?: string | null,
): ProductDetailImage[] {
  const result: ProductDetailImage[] = [];

  if (images && images.length > 0) {
    for (const img of images) {
      result.push({ url: img.url, alt: img.alt ?? "", isMain: !!img.is_main });
    }
  }

  // Если main_image есть, но его нет в images — добавляем как главное.
  if (mainImage && !result.some((img) => img.url === mainImage)) {
    result.unshift({ url: mainImage, alt: "", isMain: true });
  }

  return result;
}

// --- public ---

export async function getProduct(slug: string): Promise<ProductDetail | null> {
  const base = (process.env.INTERNAL_API_BASE_URL ?? "").replace(/\/$/, "");
  if (!base) return null;

  const res = await fetch(`${base}/api/catalog/products/${slug}/`, {
    cache: "no-store",
    headers: SSR_HEADERS,
  });

  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Product fetch failed: ${res.status}`);
  }

  const ap = (await res.json()) as ApiProductDetail;

  const final = num(ap.price);
  const old = num(ap.old_price);
  const hasDiscount = old != null && final != null && old > final;

  const attrs = ap.attributes ?? [];

  return {
    id: ap.id,
    name: ap.name,
    slug: ap.slug,
    brand: ap.brand ?? "",
    category: ap.category
      ? { name: ap.category.name, slug: ap.category.slug }
      : null,
    price: {
      final,
      old: hasDiscount ? old : undefined,
      discountPct:
        hasDiscount ? Math.round((1 - final! / old!) * 100) : undefined,
      currency: (ap.currency as "RUB") || "RUB",
    },
    stock: mapStock(ap.stock_status),
    mainImage: ap.main_image ?? undefined,
    shortDescription: ap.short_description ?? undefined,
    description: ap.description ?? undefined,
    metaTitle: ap.meta_title ?? undefined,
    metaDescription: ap.meta_description ?? undefined,
    images: mapImages(ap.images, ap.main_image),
    specs: attrs
      .map((a) => ({ label: a.name, value: formatSpecValue(a.value, a.unit) }))
      .filter((s) => s.value),
    badges: hasDiscount ? ["sale"] : [],
    breadcrumb: ap.breadcrumb ?? [],
  };
}
