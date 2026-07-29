"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { ProductImageData } from "@/lib/types";
import { ProductImage } from "./ProductImage";
import { Lightbox } from "./Lightbox";

// На десктопе главное фото ограничено по высоте, а не квадратом во всю колонку:
// квадрат 700×700 был выше всей правой колонки с ценой, и под ней оставалась
// пустая полоса в пол-экрана. На мобильном квадрат сохраняется — там колонка одна.
const MAIN_PHOTO_SIZE = "lg:aspect-auto lg:h-[520px]";

// Галерея PDP: главное фото (приоритетная загрузка — LCP) + миниатюры с выбором.
// Главное фото открывается на весь экран (Lightbox); листание — стрелками/свайпом.
// Пустой images → ProductImage сам покажет плейсхолдер. Одна картинка → без миниатюр.
export function ProductGallery({ images, name }: { images: ProductImageData[]; name: string }) {
  const [active, setActive] = useState(0);
  const [lightbox, setLightbox] = useState(false);
  const touchX = useRef<number | null>(null);
  const current = images[active];
  const hasImages = images.length > 0;

  const go = (delta: number) => {
    if (!hasImages) return;
    setActive((a) => (a + delta + images.length) % images.length);
  };

  return (
    <div className="flex flex-col gap-3">
      {hasImages ? (
        <button
          type="button"
          aria-label="Открыть фото на весь экран"
          className="block cursor-zoom-in"
          onClick={() => setLightbox(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") {
              e.preventDefault();
              go(-1);
            } else if (e.key === "ArrowRight") {
              e.preventDefault();
              go(1);
            }
          }}
          onTouchStart={(e) => {
            touchX.current = e.touches[0].clientX;
          }}
          onTouchEnd={(e) => {
            if (touchX.current == null) return;
            const dx = e.changedTouches[0].clientX - touchX.current;
            if (dx > 50) go(-1);
            else if (dx < -50) go(1);
            touchX.current = null;
          }}
        >
          <ProductImage
            src={current?.url}
            alt={current?.alt || name}
            priority
            className={MAIN_PHOTO_SIZE}
          />
        </button>
      ) : (
        <ProductImage src={undefined} alt={name} priority className={MAIN_PHOTO_SIZE} />
      )}

      {images.length > 1 && (
        <ul className="grid grid-cols-5 gap-2" aria-label="Миниатюры">
          {images.map((img, i) => (
            <li key={`${img.url}-${i}`}>
              <button
                type="button"
                onClick={() => setActive(i)}
                aria-label={`Фото ${i + 1}`}
                aria-current={i === active}
                tabIndex={i === active ? 0 : -1}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight") {
                    e.preventDefault();
                    go(1);
                  } else if (e.key === "ArrowLeft") {
                    e.preventDefault();
                    go(-1);
                  }
                }}
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

      {lightbox && (
        <Lightbox
          images={images}
          index={active}
          name={name}
          onClose={() => setLightbox(false)}
          onIndexChange={setActive}
        />
      )}
    </div>
  );
}
