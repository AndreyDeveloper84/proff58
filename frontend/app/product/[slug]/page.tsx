import { notFound } from "next/navigation";
import { getProduct } from "@/lib/product";
import { ProductGallery } from "@/components/product/ProductGallery";
import { ProductBreadcrumb } from "@/components/product/ProductBreadcrumb";
import { ProductPrice } from "@/components/product/ProductPrice";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { ProductBadges } from "@/components/product/ProductBadges";
import { ProductSpecs } from "@/components/product/ProductSpecs";
import { AddToCartButton } from "@/components/product/AddToCartButton";

type Props = {
  params: Promise<{ slug: string }>;
};

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) return {};

  return {
    title: product.metaTitle || product.name,
    description:
      product.metaDescription ||
      product.shortDescription ||
      product.description?.slice(0, 160),
  };
}

export default async function ProductPage({ params }: Props) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) notFound();

  const hasPrice = product.price.final != null;

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Хлебные крошки */}
      <div className="mb-6">
        <ProductBreadcrumb
          breadcrumb={product.breadcrumb}
          productName={product.name}
        />
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        {/* Левая колонка — галерея */}
        <div className="relative">
          <ProductBadges
            badges={product.badges}
            discountPct={product.price.discountPct}
          />
          <ProductGallery images={product.images} />
        </div>

        {/* Правая колонка — информация */}
        <div className="flex flex-col gap-4">
          {/* Бренд */}
          {product.brand && (
            <span className="text-sm text-ink-3">{product.brand}</span>
          )}

          {/* Название */}
          <h1 className="font-display text-2xl font-bold text-ink sm:text-3xl">
            {product.name}
          </h1>

          {/* Наличие */}
          <ProductAvailability stock={product.stock} />

          {/* Цена */}
          <div className="flex items-center gap-4">
            <ProductPrice price={product.price} />
          </div>

          {/* Кнопка покупки — полноразмерная на PDP */}
          <div className="flex gap-3">
            <AddToCartButton
              productId={product.id}
              stock={product.stock}
              hasPrice={hasPrice}
            />
          </div>

          {/* Краткое описание */}
          {product.shortDescription && (
            <p className="text-sm leading-relaxed text-ink-2">
              {product.shortDescription}
            </p>
          )}

          {/* Характеристики — таблица */}
          {product.specs.length > 0 && (
            <div className="mt-2">
              <h2 className="mb-3 font-display text-lg font-semibold text-ink">
                Характеристики
              </h2>
              <dl className="divide-y divide-line rounded-lg border border-line">
                {product.specs.map((spec) => (
                  <div
                    key={spec.label}
                    className="flex justify-between gap-4 px-4 py-2.5 text-sm"
                  >
                    <dt className="text-ink-3">{spec.label}</dt>
                    <dd className="text-right font-medium text-ink">
                      {spec.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      </div>

      {/* Полное описание */}
      {product.description && (
        <section className="mt-10">
          <h2 className="mb-4 font-display text-xl font-semibold text-ink">
            Описание
          </h2>
          <div className="prose prose-invert max-w-none text-sm leading-relaxed text-ink-2">
            {product.description}
          </div>
        </section>
      )}
    </main>
  );
}
