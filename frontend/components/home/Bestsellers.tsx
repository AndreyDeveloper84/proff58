"use client";

import Link from "next/link";
import { useRef } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { ProductCard } from "@/components/product/ProductCard";
import { Reveal } from "@/components/motion/Reveal";
import type { Product } from "@/lib/types";

type BestsellersProps = {
  products: Product[];
  /** Что именно в блоке: реальные продажи или новинки. Определяет подпись. */
  kind?: "bestsellers" | "new";
};

// Подпись обязана соответствовать данным: пока продаж нет, блок называет себя
// новинками, а не «хитами». Раньше здесь всегда стояло «Хиты продаж», хотя
// приходила выдача ?sort=new — витрина вводила покупателя в заблуждение.
const TITLE: Record<"bestsellers" | "new", string> = {
  bestsellers: "Хиты продаж",
  new: "Новинки каталога",
};

export function Bestsellers({ products, kind = "bestsellers" }: BestsellersProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  if (!products.length) return null;

  const scrollBy = (dir: 1 | -1) => {
    trackRef.current?.scrollBy({ left: dir * 280, behavior: "smooth" });
  };

  return (
    <section className="mx-auto max-w-[1400px] px-4 pt-2.5">
      <div className="mb-1.5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <h2 className="font-sans text-lg font-bold text-ink">{TITLE[kind]}</h2>
          <Link href="/catalog" className="hidden items-center gap-1 text-xs font-medium text-accent transition hover:opacity-80 sm:inline-flex">
            Смотреть все
            <ArrowRight className="h-3 w-3" aria-hidden />
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            className="grid h-11 w-11 place-items-center rounded-full border border-line sm:h-7 sm:w-7 text-ink-2 transition hover:border-accent hover:text-accent"
            aria-label="Прокрутить влево"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            className="grid h-11 w-11 place-items-center rounded-full border border-line sm:h-7 sm:w-7 text-ink-2 transition hover:border-accent hover:text-accent"
            aria-label="Прокрутить вправо"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      <Reveal>
        <div
          ref={trackRef}
          className="flex snap-x snap-mandatory items-stretch gap-2.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {products.map((p) => (
            <div
              key={p.id}
              className="flex w-[205px] shrink-0 snap-start lg:w-[calc((100%-50px)/6)]"
            >
              <ProductCard product={p} variant="home" className="w-full" />
            </div>
          ))}
        </div>
      </Reveal>

      <Link
        href="/catalog"
        className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent sm:hidden"
      >
        Смотреть все
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </section>
  );
}
