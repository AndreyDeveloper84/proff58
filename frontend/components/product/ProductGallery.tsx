"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ProductImageData } from "@/lib/types";
import { ProductImage } from "./ProductImage";

// Галерея PDP: главное фото + миниатюры с выбором. Пустой images → ProductImage сам покажет
// плейсхолдер «Фото готовится». Одна картинка → миниатюры не показываем.
export function ProductGallery({ images, name }: { images: ProductImageData[]; name: string }) {
  const [active, setActive] = useState(0);
  const current = images[active];

  return (
    <div className="flex flex-col gap-3">
      <ProductImage src={current?.url} alt={current?.alt || name} />
      {images.length > 1 && (
        <ul className="grid grid-cols-5 gap-2" aria-label="Миниатюры">
          {images.map((img, i) => (
            <li key={`${img.url}-${i}`}>
              <button
                type="button"
                onClick={() => setActive(i)}
                aria-label={`Фото ${i + 1}`}
                aria-current={i === active}
                className={cn(
                  "block w-full overflow-hidden rounded-md border transition-colors",
                  i === active ? "border-accent" : "border-line hover:border-accent/60",
                )}
              >
                <ProductImage src={img.url} alt={img.alt || `${name} — фото ${i + 1}`} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
