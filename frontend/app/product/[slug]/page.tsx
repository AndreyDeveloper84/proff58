import { notFound } from "next/navigation";
import { Star } from "lucide-react";
import { getProduct } from "@/lib/catalog";
import { pluralize } from "@/lib/format";
import { ProductGallery } from "@/components/product/ProductGallery";
import { ProductPrice } from "@/components/product/ProductPrice";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { ProductBadges } from "@/components/product/ProductBadges";
import { OrderCta } from "@/components/product/OrderCta";
import { CompatibilitySections } from "@/components/product/CompatibilitySections";
import { ProductReviews } from "@/components/product/ProductReviews";
import { StickyBuyBar } from "@/components/product/StickyBuyBar";
import { ProductJsonLd } from "@/components/product/ProductJsonLd";
import { Collapsible } from "@/components/product/Collapsible";
import { ShareButton } from "@/components/product/ShareButton";
import { ProductVideo } from "@/components/product/ProductVideo";

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
  const reviews = await fetchProductReviewsSafe(slug);

  // Главная → Каталог → …категории (из breadcrumb)… → Товар (последний — текст, без ссылки).
  const crumbs = [
    { label: "Главная", href: "/" },
    { label: "Каталог", href: "/catalog" },
    ...product.breadcrumb.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` })),
  ];

  // Длинные характеристики/описание сворачиваем (порог по объёму).
  const specsDl = (
    <dl className="divide-y divide-line rounded-lg border border-line">
      {product.specs.map((s, i) => (
        // #574: на 320px жёсткие 50/50 ломали длинные значения («SDS-Max, 1500 Вт»)
        // — до sm характеристики идут в две строки, дальше в две колонки.
        <div
          key={`${s.label}-${i}`}
          className="flex flex-col gap-0.5 px-3 py-2 text-sm sm:flex-row sm:gap-3"
        >
          <dt className="text-ink-3 sm:w-1/2">{s.label}</dt>
          <dd className="text-ink-2 sm:w-1/2">{s.value}</dd>
        </div>
      ))}
    </dl>
  );

  const descriptionBlock = product.description ? (
    <p className="whitespace-pre-line text-sm leading-relaxed text-ink-2">
      {product.description}
    </p>
  ) : null;

  return (
    // #574: нижний отступ под липкую панель покупки — иначе она перекрывала
    // последнюю карточку отзывов.
    <main className="mx-auto w-full max-w-[1400px] px-4 pb-28 pt-5 sm:px-6 lg:px-8 lg:pt-7">
      <ProductJsonLd product={product} crumbs={crumbs} />
      <nav
        aria-label="Хлебные крошки"
        className="mb-4 flex flex-wrap items-center gap-1.5 text-xs text-ink-3"
      >
        {crumbs.map((b, i) => (
          <span key={`${b.href}-${i}`} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden>›</span>}
            <a href={b.href} className="hover:text-accent">
              {b.label}
            </a>
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span aria-hidden>›</span>
          <span className="text-ink-2">{product.name}</span>
        </span>
      </nav>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.08fr)_minmax(420px,.92fr)] lg:gap-8">
        <ProductGallery images={product.images} name={product.name} />

        <div className="flex flex-col gap-4">
          {product.brand && <span className="text-sm text-ink-3">{product.brand}</span>}
          <h1 className="font-display text-2xl font-semibold leading-tight text-ink lg:text-[30px]">
            {product.name}
          </h1>
          {/* #574: рейтинг рядом с названием — раньше отзывы были только внизу
              страницы, и понять «есть ли оценки» до скролла было нельзя. Блок
              скрыт при нулевом количестве (docs/design/pages/pdp.md: не рисуем
              «0 отзывов» как тупик). */}
          {reviews && reviews.summary.count > 0 && (
            <a
              href="#reviews"
              className="flex w-fit items-center gap-2 text-sm text-ink-2 hover:text-accent"
            >
              <Star className="h-4 w-4 fill-amber-400 text-amber-400" aria-hidden />
              <span className="font-semibold text-ink">
                {(reviews.summary.product_rating_avg ?? 0).toFixed(1)}
              </span>
              <span className="underline-offset-2 hover:underline">
                {reviews.summary.count}{" "}
                {pluralize(reviews.summary.count, "отзыв", "отзыва", "отзывов")}
              </span>
            </a>
          )}
          <div className="flex items-center justify-between gap-3">
            <ProductBadges badges={product.badges} discountPct={product.price.discountPct} />
            <ShareButton title={product.name} />
          </div>
          <ProductAvailability stock={product.stock} stockQty={product.stockQty} />
          <div
            id="buybox-anchor"
            className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-line bg-surface p-4 lg:p-5"
          >
            <ProductPrice price={product.price} />
            <OrderCta
              productId={product.id}
              productSlug={product.slug}
              stock={product.stock}
              hasPrice={product.price.final != null}
            />
          </div>

        </div>
      </div>

      {(product.specs.length > 0 || product.description) && (
        <section className="mt-8 overflow-hidden rounded-lg border border-line bg-surface">
          <nav
            aria-label="Разделы карточки товара"
            className="flex gap-6 overflow-x-auto border-b border-line px-4 text-sm font-semibold text-ink-2 sm:px-5"
          >
            {product.specs.length > 0 && (
              <a
                href="#characteristics"
                className="min-h-12 shrink-0 border-b-2 border-accent py-3.5 text-ink"
              >
                Характеристики
              </a>
            )}
            {product.description && (
              <a href="#description" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                Описание
              </a>
            )}
            {product.compatible && (
              <a href="#compatible" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                Совместимые товары
              </a>
            )}
            {reviews && (
              <a href="#reviews" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                Отзывы {reviews.summary.count || ""}
              </a>
            )}
          </nav>

          <div className="grid gap-6 p-4 sm:p-5 lg:grid-cols-[1.08fr_.92fr] lg:gap-8">
            {product.specs.length > 0 && (
              <div id="characteristics" className="scroll-mt-28">
                <h2 className="mb-3 text-lg font-semibold text-ink">Характеристики</h2>
                {product.specs.length > 8 ? (
                  <Collapsible collapsedHeight={300}>{specsDl}</Collapsible>
                ) : (
                  specsDl
                )}
              </div>
            )}
            {product.description && (
              <div id="description" className="scroll-mt-28">
                <h2 className="mb-3 text-lg font-semibold text-ink">Описание</h2>
                {product.description.length > 600 ? (
                  <Collapsible collapsedHeight={240}>{descriptionBlock}</Collapsible>
                ) : (
                  descriptionBlock
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {product.videoUrl && (
        <section aria-label="Видео" className="mt-8">
          <h2 className="mb-2 font-display text-lg font-semibold text-ink">Видео</h2>
          <div className="max-w-2xl">
            <ProductVideo url={product.videoUrl} />
          </div>
        </section>
      )}

      <div id="compatible" className="mt-8 scroll-mt-28">
        <CompatibilitySections sections={product.compatible} />

        {reviews && <ProductReviews slug={slug} initial={reviews} />}
      </div>

      <StickyBuyBar product={product} />
    </main>
  );
}


// #573: отзывы — best-effort SSR (флаг off/ошибка → null → секции нет).
async function fetchProductReviewsSafe(slug: string) {
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) return null;
  const { fetchProductReviewsFromApi } = await import("@/lib/adapters");
  return fetchProductReviewsFromApi(base.replace(/\/$/, ""), slug);
}
