"use client";

import Image from "next/image";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { Reveal } from "@/components/motion/Reveal";
import { categoryAsset } from "@/lib/home-content";
import type { CategoryNode } from "@/lib/catalog";

type CategoryGridProps = { categories: CategoryNode[] };

export function CategoryGrid({ categories }: CategoryGridProps) {
  const reduce = useReducedMotion();
  const items = categories.slice(0, 6);
  if (!items.length) return null;

  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {items.map((cat, i) => (
          <Reveal key={cat.id} delay={reduce ? 0 : i * 0.05}>
            <motion.div whileHover={reduce ? undefined : { y: -4 }} className="h-full">
              <Link
                href={`/catalog/${cat.slug}`}
                className="group flex h-full flex-col overflow-hidden rounded-lg border border-line bg-surface transition hover:border-accent"
              >
                <div className="relative aspect-[4/3] overflow-hidden bg-raised">
                  <Image
                    src={categoryAsset(cat.slug)}
                    alt={cat.name}
                    fill
                    sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 16vw"
                    className="object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                </div>
                <span className="px-3 py-3 text-sm font-medium text-ink-2 transition group-hover:text-ink">
                  {cat.name}
                </span>
              </Link>
            </motion.div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
