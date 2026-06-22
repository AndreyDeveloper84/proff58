"use client";

import { useState } from "react";
import Image from "next/image";
import { Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ProductDetailImage } from "@/lib/product";

export function ProductGallery({ images }: { images: ProductDetailImage[] }) {
  const mainIdx = images.findIndex((img) => img.isMain);
  const [selected, setSelected] = useState(mainIdx >= 0 ? mainIdx : 0);

  // Нет фото — placeholder.
  if (!images.length) {
    return (
      <div className="aspect-square overflow-hidden rounded-lg bg-photo">
        <div className="flex h-full flex-col items-center justify-center gap-2 text-photo-ink">
          <Wrench className="h-12 w-12" strokeWidth={1.5} aria-hidden />
          <span className="text-sm font-medium">Фото готовится</span>
        </div>
      </div>
    );
  }

  const current = images[selected];

  return (
    <div className="flex flex-col gap-3">
      {/* Большое фото */}
      <div className="relative aspect-square overflow-hidden rounded-lg bg-photo">
        <Image
          src={current.url}
          alt={current.alt || "Фото товара"}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-contain p-4"
          priority
        />
      </div>

      {/* Миниатюры — показываем только если фото больше одного */}
      {images.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {images.map((img, idx) => (
            <button
              key={img.url}
              type="button"
              onClick={() => setSelected(idx)}
              aria-label={`Показать фото ${idx + 1}`}
              className={cn(
                "relative h-16 w-16 shrink-0 overflow-hidden rounded-md bg-photo transition-all",
                idx === selected
                  ? "ring-2 ring-accent"
                  : "opacity-70 hover:opacity-100",
              )}
            >
              <Image
                src={img.url}
                alt={img.alt || `Миниатюра ${idx + 1}`}
                fill
                sizes="64px"
                className="object-contain p-1"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
