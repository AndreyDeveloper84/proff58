"use client";

import Link from "next/link";
import { useRef } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { ProductCard } from "@/components/product/ProductCard";
import { Reveal } from "@/components/motion/Reveal";
import type { Product } from "@/lib/types";

type BestsellersProps = { products: Product[] };

export function Bestsellers({ products }: BestsellersProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  if (!products.length) return null;

  const scrollBy = (dir: 1 | -1) => {
    trackRef.current?.scrollBy({ left: dir * 280, behavior: "smooth" });
  };

  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="mb-5 flex items-end justify-between gap-4">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-wide text-ink">
          Хиты продаж
        </h2>
        <div className="flex items-center gap-2">
          <Link href="/catalog" className="hidden text-sm text-ink-2 transition hover:text-accent sm:inline">
            Смотреть все
          </Link>
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:bg-raised hover:text-ink"
            aria-label="Прокрутить влево"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:bg-raised hover:text-ink"
            aria-label="Прокрутить вправо"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      <Reveal>
        <div
          ref={trackRef}
          className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {products.map((p) => (
            <div key={p.id} className="w-[240px] shrink-0 snap-start">
              <ProductCard product={p} />
            </div>
          ))}
        </div>
      </Reveal>

      <Link
        href="/catalog"
        className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-accent sm:hidden"
      >
        Смотреть все
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </section>
  );
}
