import { notFound } from "next/navigation";
import { getProduct } from "@/lib/catalog";
import { ProductGallery } from "@/components/product/ProductGallery";
import { ProductPrice } from "@/components/product/ProductPrice";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { ProductBadges } from "@/components/product/ProductBadges";
import { OrderCta } from "@/components/product/OrderCta";
import { CompatibilitySections } from "@/components/product/CompatibilitySections";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) return { title: "Товар не найден — Профессионал" };
  return { title: `${product.name} — Профессионал` };
}

export default async function ProductPage({ params }: Props) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) notFound();

  // Главная → Каталог → …категории (из breadcrumb)… → Товар (последний — текст, без ссылки).
  const crumbs = [
    { label: "Главная", href: "/" },
    { label: "Каталог", href: "/catalog" },
    ...product.breadcrumb.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` })),
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <nav
        aria-label="Хлебные крошки"
        className="mb-4 flex flex-wrap items-center gap-1 text-xs text-ink-3"
      >
        {crumbs.map((b, i) => (
          <span key={`${b.href}-${i}`} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden>/</span>}
            <a href={b.href} className="hover:text-accent">
              {b.label}
            </a>
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span aria-hidden>/</span>
          <span className="text-ink-2">{product.name}</span>
        </span>
      </nav>

      <div className="grid gap-6 lg:grid-cols-2">
        <ProductGallery images={product.images} name={product.name} />

        <div className="flex flex-col gap-4">
          {product.brand && <span className="text-sm text-ink-3">{product.brand}</span>}
          <h1 className="font-display text-2xl font-semibold text-ink">{product.name}</h1>
          <ProductBadges badges={product.badges} discountPct={product.price.discountPct} />
          <ProductAvailability stock={product.stock} />
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-4">
            <ProductPrice price={product.price} />
            <OrderCta
              productId={product.id}
              stock={product.stock}
              hasPrice={product.price.final != null}
            />
          </div>

          {product.specs.length > 0 && (
            <section aria-label="Характеристики">
              <h2 className="mb-2 font-display text-lg font-semibold text-ink">Характеристики</h2>
              <dl className="divide-y divide-line rounded-lg border border-line">
                {product.specs.map((s, i) => (
                  <div key={`${s.label}-${i}`} className="flex gap-3 px-3 py-2 text-sm">
                    <dt className="w-1/2 text-ink-3">{s.label}</dt>
                    <dd className="w-1/2 text-ink-2">{s.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>
      </div>

      {product.description && (
        <section aria-label="Описание" className="mt-8">
          <h2 className="mb-2 font-display text-lg font-semibold text-ink">Описание</h2>
          <p className="whitespace-pre-line text-sm leading-relaxed text-ink-2">
            {product.description}
          </p>
        </section>
      )}

      <div className="mt-10">
        <CompatibilitySections sections={product.compatible} />
      </div>
    </div>
  );
}
