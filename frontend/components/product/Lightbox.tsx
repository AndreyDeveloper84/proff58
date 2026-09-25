"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import type { ProductImageData } from "@/lib/types";

// Полноэкранный просмотр фото товара: стрелки/свайп/Esc, клик по фону закрывает.
// Управляется снаружи (index/onIndexChange) — переключение синхронно с галереей.
export function Lightbox({
  images,
  index,
  name,
  onClose,
  onIndexChange,
}: {
  images: ProductImageData[];
  index: number;
  name: string;
  onClose: () => void;
  onIndexChange: (next: number) => void;
}) {
  const touchX = useRef<number | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Клавиатура: Esc закрывает, ←/→ листают. Блокируем скролл фона на время показа.
  useEffect(() => {
    const go = (delta: number) =>
      onIndexChange((index + delta + images.length) % images.length);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [index, images.length, onClose, onIndexChange]);

  // Фокус на кнопку закрытия при открытии (для клавиатуры/скринридера).
  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  const current = images[index];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${name} — просмотр фото`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90"
      onClick={onClose}
      onTouchStart={(e) => {
        touchX.current = e.touches[0].clientX;
      }}
      onTouchEnd={(e) => {
        if (touchX.current == null) return;
        const dx = e.changedTouches[0].clientX - touchX.current;
        if (dx > 50) onIndexChange((index - 1 + images.length) % images.length);
        else if (dx < -50) onIndexChange((index + 1) % images.length);
        touchX.current = null;
      }}
    >
      <button
        ref={closeRef}
        type="button"
        onClick={onClose}
        aria-label="Закрыть"
        className="absolute right-4 top-4 text-white/80 hover:text-white"
      >
        <X className="h-7 w-7" aria-hidden />
      </button>

      {images.length > 1 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange((index - 1 + images.length) % images.length);
          }}
          aria-label="Предыдущее фото"
          className="absolute left-2 text-white/80 hover:text-white sm:left-4"
        >
          <ChevronLeft className="h-9 w-9" aria-hidden />
        </button>
      )}

      <div
        className="relative h-[80vh] w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        {current?.url && (
          <Image
            src={current.url}
            alt={current.alt || name}
            fill
            sizes="90vw"
            className="object-contain"
          />
        )}
      </div>

      {images.length > 1 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange((index + 1) % images.length);
          }}
          aria-label="Следующее фото"
          className="absolute right-2 text-white/80 hover:text-white sm:right-4"
        >
          <ChevronRight className="h-9 w-9" aria-hidden />
        </button>
      )}
    </div>
  );
}
