import Image from "next/image";
import { Wrench } from "lucide-react";

// Светлая фото-зона: товар читается на тёмном каталоге. Нет фото → фирменный
// плейсхолдер «Фото готовится» (временное состояние, не дефект).
// priority — для главного фото PDP (LCP грузится сразу, без lazy).
export function ProductImage({
  src,
  alt,
  priority = false,
  sizes = "(max-width: 768px) 50vw, 25vw",
}: {
  src?: string;
  alt: string;
  priority?: boolean;
  sizes?: string;
}) {
  return (
    <div className="relative aspect-square overflow-hidden rounded-md bg-photo">
      {src ? (
        <Image
          src={src}
          alt={alt}
          fill
          sizes={sizes}
          className="object-contain p-3"
          {...(priority ? { priority: true } : { loading: "lazy" })}
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
