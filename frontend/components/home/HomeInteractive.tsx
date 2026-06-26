"use client";

import { useState } from "react";
import type { Product } from "@/lib/types";
import type { CategoryNode } from "@/lib/catalog";
import { Hero } from "./Hero";
import { CategoryGrid } from "./CategoryGrid";
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
      <CategoryGrid categories={categories} />
      <TrustBadges />
      <Bestsellers products={bestsellers} />
      <ConsultBlock onConsult={openModal} />
      <AboutStats />
      <InquiryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
