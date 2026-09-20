"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, RotateCcw, X } from "lucide-react";
import { AddToCartButton } from "@/components/product/AddToCartButton";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { ProductImage } from "@/components/product/ProductImage";
import { ProductPrice } from "@/components/product/ProductPrice";
import { keySpecs } from "@/lib/specs";
import type { Product, ProductDetail, ProductImageData } from "@/lib/types";
import { cn } from "@/lib/utils";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Подробности грузятся только по клику, по одному товару. Маршрут — уже существующий
// same-origin BFF сравнения: он отдаёт ту же карточку товара и разведён в nginx,
// новый путь (и правка nginx) ради этого не нужен. Адрес Django в браузер не попадает.
async function loadDetail(slug: string, signal: AbortSignal): Promise<ProductDetail> {
  const res = await fetch(`/api/catalog/compare?slugs=${encodeURIComponent(slug)}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`quick view ${res.status}`);
  const json = (await res.json()) as { products?: ProductDetail[] };
  const detail = json.products?.find((p) => p.slug === slug);
  if (!detail) throw new Error("quick view: товар не найден");
  return detail;
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; detail: ProductDetail }
  | { status: "error" };

function Gallery({ images, name }: { images: ProductImageData[]; name: string }) {
  const [active, setActive] = useState(0);
  const touchX = useRef<number | null>(null);
  const index = Math.min(active, Math.max(images.length - 1, 0));
  const go = (delta: number) =>
    images.length > 1 && setActive((a) => (a + delta + images.length) % images.length);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div
        className="relative"
        onTouchStart={(e) => {
          touchX.current = e.touches[0].clientX;
        }}
        onTouchEnd={(e) => {
          if (touchX.current == null) return;
          const dx = e.changedTouches[0].clientX - touchX.current;
          if (dx > 50) go(-1);
          else if (dx < -50) go(1);
          touchX.current = null;
        }}
      >
        <ProductImage
          src={images[index]?.url}
          alt={images[index]?.alt || name}
          className="aspect-square w-full sm:aspect-[4/3] lg:aspect-square"
        />
        {images.length > 1 && (
          <>
            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Предыдущее фото"
              className="absolute left-2 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full bg-card/90 text-ink shadow-card hover:text-accent"
            >
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Следующее фото"
              className="absolute right-2 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full bg-card/90 text-ink shadow-card hover:text-accent"
            >
              <ChevronRight className="h-5 w-5" aria-hidden />
            </button>
          </>
        )}
      </div>
      {images.length > 1 && (
        <ul className="flex gap-2 overflow-x-auto pb-1" aria-label="Миниатюры">
          {images.map((img, i) => (
            <li key={`${img.url}-${i}`} className="w-16 shrink-0">
              <button
                type="button"
                onClick={() => setActive(i)}
                aria-label={`Фото ${i + 1}`}
                aria-current={i === index}
                className={cn(
                  "block w-full overflow-hidden rounded-md border transition-colors",
                  i === index ? "border-accent" : "border-line hover:border-accent/60",
                )}
              >
                <ProductImage src={img.url} alt="" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Окно быстрого просмотра. Название, цена и наличие показываются СРАЗУ — они уже есть
 * в карточке списка; галерея и характеристики догружаются. На телефоне окно занимает
 * весь экран, на широком — центрировано.
 */
export function QuickViewDialog({ product, onClose }: { product: Product; onClose: () => void }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const href = `/product/${product.slug}`;
  const title = product.name;

  // Загрузка. Отмена по размонтированию/повтору защищает от ответа предыдущего товара:
  // при быстром переключении карточек устаревший ответ прерывается и в окно не попадает
  // (плюс key={product.id} в провайдере даёт каждому товару своё состояние, поэтому
  // начальное «loading» не нужно выставлять в эффекте — оно и так начальное).
  useEffect(() => {
    const controller = new AbortController();
    loadDetail(product.slug, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) setState({ status: "ready", detail });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error" });
      });
    return () => controller.abort();
  }, [product.slug, attempt]);

  // Блокировка прокрутки фона: список под окном стоит на месте и после закрытия
  // оказывается ровно там, где его оставили.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  // Клавиши слушаем на document, а не на самом окне. Кнопка покупки на время запроса
  // становится disabled, браузер снимает с неё фокус на <body> — и обработчик,
  // висящий на окне, переставал получать Escape и Tab: окно нельзя было закрыть с
  // клавиатуры сразу после покупки. С document ловушка работает, где бы ни был фокус.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      const nodes = dialog?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!dialog || !nodes || nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const current = document.activeElement;
      const outside = !dialog.contains(current);
      if (event.shiftKey && (current === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (current === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [onClose]);

  const detail = state.status === "ready" ? state.detail : null;
  // Пока подробности грузятся — фото из карточки списка, чтобы окно не было пустым.
  const images: ProductImageData[] =
    detail?.images ?? (product.image ? [{ url: product.image, alt: title, isMain: true }] : []);
  const shown = detail ?? product;
  const specs = keySpecs(shown.specs, 6);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-stretch justify-center bg-black/55 sm:items-center sm:p-6"
      onClick={onClose}
      data-testid="quick-view-backdrop"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-view-title"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full flex-col overflow-hidden bg-surface shadow-xl sm:h-auto sm:max-h-[calc(100dvh-3rem)] sm:max-w-4xl sm:rounded-lg sm:border sm:border-line"
      >
        {/* Шапка закреплена: закрытие доступно при любой длине содержимого. */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-2 sm:px-6">
          <p className="text-sm font-medium text-ink-3">Быстрый просмотр</p>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Закрыть быстрый просмотр"
            className="-mr-2 grid h-11 w-11 place-items-center rounded-md text-ink-2 hover:bg-raised hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-8">
            <Gallery images={images} name={title} />

            <div className="flex min-w-0 flex-col">
              {shown.brand && <p className="text-sm text-ink-3">{shown.brand}</p>}
              <h2
                id="quick-view-title"
                className="mt-0.5 break-words font-display text-xl font-semibold leading-snug text-ink sm:text-2xl"
              >
                {title}
              </h2>

              <div className="mt-3">
                <ProductAvailability stock={shown.stock} stockQty={shown.stockQty} />
              </div>
              <div className="mt-2">
                <ProductPrice price={shown.price} />
              </div>

              <div className="mt-4">
                <AddToCartButton
                  productId={product.id}
                  productSlug={product.slug}
                  stock={shown.stock}
                  hasPrice={shown.price.final != null}
                  fullWidth
                  showLabel
                />
              </div>

              <section className="mt-5" aria-labelledby="quick-view-specs">
                <h3 id="quick-view-specs" className="text-base font-semibold text-ink">
                  Основные характеристики
                </h3>
                {state.status === "loading" && specs.length === 0 ? (
                  <div className="mt-2 space-y-2" role="status" aria-label="Загружаем характеристики">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="h-5 animate-pulse rounded bg-raised" />
                    ))}
                  </div>
                ) : specs.length > 0 ? (
                  <dl className="mt-2 divide-y divide-line">
                    {specs.map((spec) => (
                      <div
                        key={spec.slug ?? spec.label}
                        className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 py-2 text-[15px]"
                      >
                        <dt className="min-w-0 break-words text-ink-3">{spec.label}</dt>
                        <dd className="min-w-0 break-words text-right font-medium text-ink">
                          {spec.value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="mt-2 text-sm text-ink-3">
                    Характеристики этого товара ещё не заполнены. Уточните их у менеджера.
                  </p>
                )}
              </section>

              {state.status === "error" && (
                <div
                  role="alert"
                  className="mt-4 rounded-md border border-danger/30 bg-danger/10 px-3 py-3 text-sm text-danger"
                >
                  <p>Не удалось загрузить фото и характеристики. Цена и наличие — из списка.</p>
                  <button
                    type="button"
                    onClick={() => {
                      setState({ status: "loading" });
                      setAttempt((n) => n + 1);
                    }}
                    className="mt-2 inline-flex min-h-11 items-center gap-2 font-semibold underline-offset-2 hover:underline"
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden />
                    Повторить
                  </button>
                </div>
              )}

              <Link
                href={href}
                onClick={onClose}
                className="mt-5 inline-flex min-h-11 items-center gap-2 text-base font-semibold text-accent hover:underline"
              >
                Подробнее о товаре
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
