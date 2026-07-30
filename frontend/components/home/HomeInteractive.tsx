"use client";

import { useState } from "react";
import type { Product } from "@/lib/types";
import type { ResolvedStorefront } from "@/lib/site";
import { Hero } from "./Hero";
import { HomeIntentGrid } from "./HomeIntentGrid";
import { PopularBrands } from "./PopularBrands";
import { Bestsellers } from "./Bestsellers";
import { HomeBottom } from "./HomeBottom";
import { InquiryModal } from "./InquiryModal";

type HomeInteractiveProps = {
  bestsellers: { products: Product[]; kind: "bestsellers" | "new" };
  storefront: ResolvedStorefront;
};

export function HomeInteractive({ bestsellers, storefront }: HomeInteractiveProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const openModal = () => setModalOpen(true);

  return (
    <>
      <Hero onConsult={openModal} maxHref={storefront.maxHref} />
      <HomeIntentGrid />
      {/* Ряд «Популярные категории» убран: популярности за ним не стояло —
          это были первые семь корневых категорий в алфавитном порядке, из-за
          чего в магазине электроинструмента не было электроинструмента. */}
      <Bestsellers products={bestsellers.products} kind={bestsellers.kind} />
      <PopularBrands />
      {/* #590: нижняя зона по макету — «почему покупают» + статьи + подписка.
          TrustBadges/ConsultBlock/AboutStats с главной убраны: в макете их нет
          (их роль выполняют hero-CTA и WhyBuy), компоненты остаются в кодовой
          базе для других страниц. */}
      <HomeBottom />
      <InquiryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
