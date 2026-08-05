import { notFound } from "next/navigation";
import { MessageSquareText, ShieldCheck, Star } from "lucide-react";
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
import { CompareButton } from "@/components/product/CompareButton";
import { ShareButton } from "@/components/product/ShareButton";
import { ProductVideo } from "@/components/product/ProductVideo";
import { ProductDetailsShowcase } from "@/components/product/ProductDetailsShowcase";
import { SpecChips } from "@/components/product/SpecChips";
import { SITE } from "@/lib/site";

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

  // Вкладка связанных товаров. Раньше она появлялась при любом непустом объекте
  // секций — даже когда все пять пусты, и вела в никуда. Подпись зависит от того,
  // что там на самом деле: «покупают вместе» и аналоги интереснее совместимости.
  const related = product.compatible;
  const hasRelated = related != null && Object.values(related).some((items) => items.length > 0);
  const relatedTabLabel = !hasRelated
    ? null
    : related.crossSell.length || related.analogs.length
      ? "Смотрите также"
      : "Совместимые товары";

  // Главная → Каталог → …категории (из breadcrumb)… → Товар (последний — текст, без ссылки).
  const crumbs = [
    { label: "Главная", href: "/" },
    { label: "Каталог", href: "/catalog" },
    ...product.breadcrumb.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` })),
  ];

  return (
    // #574: нижний отступ под липкую панель покупки — иначе она перекрывала
    // последнюю карточку отзывов.
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-28 pt-5 sm:px-6 lg:px-8 lg:pt-7">
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
        {/* Название товара в крошках — только с sm. На телефоне оно занимало
            две строки из четырёх и дублировало заголовок, который идёт следом;
            в разметке для поисковиков (ProductJsonLd) цепочка остаётся полной. */}
        <span className="hidden items-center gap-1 sm:flex">
          <span aria-hidden>›</span>
          <span className="text-ink-2">{product.name}</span>
        </span>
      </nav>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.08fr)_minmax(420px,.92fr)] lg:gap-8">
        <div className="flex flex-col gap-3">
          <ProductGallery images={product.images} name={product.name} />
          {/* Паспортные чипы под фото (макет pdp-v4): «800 Вт · 3 Дж · SDS-plus».
              Читаются раньше всего остального — покупатель сверяет параметры
              прежде, чем смотреть цену. */}
          <SpecChips specs={product.specs} />
        </div>

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
              <Star className="h-4 w-4 fill-current text-rating" aria-hidden />
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
            <div className="flex items-center gap-2">
              <CompareButton slug={product.slug} variant="wide" />
              <ShareButton title={product.name} />
            </div>
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

          {/* Обещания магазина под ценой. «Коротко о товаре» отсюда убрано:
              выжимку характеристик теперь держит блок «Главное в работе», и
              две таблицы подряд только спорили друг с другом. */}
          <div className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
            <div className="flex items-start gap-2.5">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
              <span>
                <strong className="block text-sm font-semibold text-ink">
                  Официальная продукция
                </strong>
                <span className="mt-0.5 block text-xs text-ink-3">Только официальные поставки</span>
              </span>
            </div>
            <a href={SITE.phone.href} className="flex items-start gap-2.5 hover:text-accent">
              <MessageSquareText className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
              <span>
                <strong className="block text-sm font-semibold text-ink">
                  Экспертная консультация
                </strong>
                <span className="mt-0.5 block text-xs text-ink-3">Поможем с выбором инструмента</span>
              </span>
            </a>
          </div>
        </div>
      </div>

      {(product.specs.length > 0 || product.description) && (
        <section className="mt-8 overflow-hidden rounded-lg border border-line bg-surface">
          <nav
            aria-label="Разделы карточки товара"
            className="flex gap-6 overflow-x-auto border-b border-line bg-surface px-4 text-sm font-semibold text-ink-2 sm:px-5"
          >
            <a
              href="#overview"
              className="min-h-12 shrink-0 border-b-2 border-accent py-3.5 text-ink"
            >
              О товаре
            </a>
            {product.specs.length > 0 && (
              <a href="#characteristics" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                Характеристики
              </a>
            )}
            {product.description && (
              <a href="#description" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                Описание
              </a>
            )}
            {relatedTabLabel && (
              <a href="#compatible" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                {relatedTabLabel}
              </a>
            )}
            {reviews && (
              <a href="#reviews" className="min-h-12 shrink-0 py-3.5 hover:text-accent">
                Отзывы {reviews.summary.count || ""}
              </a>
            )}
          </nav>

          <div id="overview" className="scroll-mt-28 bg-raised p-4 sm:p-5 lg:p-6">
            <ProductDetailsShowcase product={product} />
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
