"use client";

import { useState } from "react";
import type { Product } from "@/lib/types";
import type { CategoryNode } from "@/lib/catalog";
import type { ResolvedStorefront } from "@/lib/site";
import { Hero } from "./Hero";
import { HomeIntentGrid } from "./HomeIntentGrid";
import { PopularCategories } from "./PopularCategories";
import { PopularBrands } from "./PopularBrands";
import { Bestsellers } from "./Bestsellers";
import { HomeBottom } from "./HomeBottom";
import { InquiryModal } from "./InquiryModal";

type HomeInteractiveProps = {
  categories: CategoryNode[];
  bestsellers: Product[];
  storefront: ResolvedStorefront;
};

export function HomeInteractive({ categories, bestsellers, storefront }: HomeInteractiveProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const openModal = () => setModalOpen(true);

  return (
    <>
      <Hero onConsult={openModal} maxHref={storefront.maxHref} />
      <HomeIntentGrid />
      {/* #589: порядок витрины по макету — хиты → категории (pill'ы) → бренды.
          Крупные плитки CategoryGrid на главной заменены pill-рядом. */}
      <Bestsellers products={bestsellers} maxHref={storefront.maxHref} />
      <PopularCategories categories={categories} />
      <PopularBrands />
      {/* #590: нижняя зона по макету — «почему покупают» + статьи + подписка +
          MAX-карточка. TrustBadges/ConsultBlock/AboutStats с главной убраны:
          в макете их нет (их роль выполняют hero-CTA и WhyBuy), компоненты
          остаются в кодовой базе для других страниц. */}
      <HomeBottom maxHref={storefront.maxHref} />
      <InquiryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
