"use client";

import { useState } from "react";
import type { Product } from "@/lib/types";
import { Hero } from "./Hero";
import { HomeIntentGrid } from "./HomeIntentGrid";
import { PopularBrands } from "./PopularBrands";
import { Bestsellers } from "./Bestsellers";
import { HomeBottom } from "./HomeBottom";
import { InquiryModal } from "./InquiryModal";

type HomeInteractiveProps = {
  bestsellers: { products: Product[]; kind: "bestsellers" | "new" };
};

export function HomeInteractive({ bestsellers }: HomeInteractiveProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const openModal = () => setModalOpen(true);

  return (
    <>
      <Hero onConsult={openModal} />
      <HomeIntentGrid />
      {/* Ряд «Популярные категории» убран: популярности за ним не стояло —
          это были первые семь корневых категорий в алфавитном порядке, из-за
          чего в магазине электроинструмента не было электроинструмента. */}
      <Bestsellers products={bestsellers.products} kind={bestsellers.kind} />
      <PopularBrands />
      {/* #590: нижняя зона по макету — «почему покупают» + статьи + подписка. */}
      <HomeBottom />
      <InquiryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
