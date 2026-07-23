"use client";

import { useState } from "react";
import type { Product } from "@/lib/types";
import type { CategoryNode } from "@/lib/catalog";
import { Hero } from "./Hero";
import { HomeIntentGrid } from "./HomeIntentGrid";
import { HomeServiceStrip } from "./HomeServiceStrip";
import { PopularCategories } from "./PopularCategories";
import { PopularBrands } from "./PopularBrands";
import { TrustBadges } from "./TrustBadges";
import { Bestsellers } from "./Bestsellers";
import { ConsultBlock } from "./ConsultBlock";
import { AboutStats } from "./AboutStats";
import { InquiryModal } from "./InquiryModal";

type HomeInteractiveProps = {
  categories: CategoryNode[];
  bestsellers: Product[];
};

export function HomeInteractive({ categories, bestsellers }: HomeInteractiveProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const openModal = () => setModalOpen(true);

  return (
    <>
      <Hero onConsult={openModal} />
      <HomeIntentGrid />
      <HomeServiceStrip />
      {/* #589: порядок витрины по макету — хиты → категории (pill'ы) → бренды.
          Крупные плитки CategoryGrid на главной заменены pill-рядом. */}
      <Bestsellers products={bestsellers} />
      <PopularCategories categories={categories} />
      <PopularBrands />
      <TrustBadges />
      <ConsultBlock onConsult={openModal} />
      <AboutStats />
      <InquiryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
