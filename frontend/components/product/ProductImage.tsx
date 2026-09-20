import Image from "next/image";
import { Wrench } from "lucide-react";
import { cn } from "@/lib/utils";

// Светлая фото-зона: товар читается на тёмном каталоге. Нет фото → фирменный
// плейсхолдер «Фото готовится» (временное состояние, не дефект).
// priority — для главного фото PDP (LCP грузится сразу, без lazy).
export function ProductImage({
  src,
  alt,
  priority = false,
  sizes = "(max-width: 768px) 50vw, 25vw",
  className,
}: {
  src?: string;
  alt: string;
  priority?: boolean;
  sizes?: string;
  className?: string;
}) {
  return (
    <div
      className={cn("@container relative aspect-square overflow-hidden rounded-md bg-photo", className)}
    >
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
          {/* В миниатюре (корзина, 72 px) подпись 12 px не помещается и ломалась на две
              строки с обрезкой — там остаётся только значок, текст читает скринридер. */}
          <span className="sr-only px-1 text-center text-xs font-medium leading-tight @[110px]:not-sr-only">
            Фото готовится
          </span>
        </div>
      )}
    </div>
  );
}
