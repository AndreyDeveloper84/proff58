import Image from "next/image";
import { Wrench } from "lucide-react";

// Светлая фото-зона: товар читается на тёмном каталоге. Нет фото → фирменный
// плейсхолдер «Фото готовится» (временное состояние, не дефект).
export function ProductImage({ src, alt }: { src?: string; alt: string }) {
  return (
    <div className="relative aspect-square overflow-hidden rounded-md bg-photo">
      {src ? (
        <Image
          src={src}
          alt={alt}
          fill
          sizes="(max-width: 768px) 50vw, 25vw"
          className="object-contain p-3"
          loading="lazy"
        />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-1.5 text-photo-ink">
          <Wrench className="h-7 w-7" strokeWidth={1.5} aria-hidden />
          <span className="text-[11px] font-medium">Фото готовится</span>
        </div>
      )}
    </div>
  );
}
