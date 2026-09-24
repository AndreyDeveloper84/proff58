import Image from "next/image";
import { Wrench } from "lucide-react";
import { cn } from "@/lib/utils";

// Светлая фото-зона: товар читается на тёмном каталоге. Нет фото → фирменный
// плейсхолдер «Фото готовится» (временное состояние, не дефект).
// priority — для главного фото PDP (LCP грузится сразу, без lazy).
// normalized — фото уже прошло автообработку (белый холст 1200×1200, встроенные
// поля 7%): свой отступ не добавляем, иначе поле удваивается. Обычный исходник
// (false/не передан) получает небольшой отступ — меньше прежних 12px, но не ноль.
export function ProductImage({
  src,
  alt,
  priority = false,
  sizes = "(max-width: 768px) 50vw, 25vw",
  className,
  normalized = false,
}: {
  src?: string;
  alt: string;
  priority?: boolean;
  sizes?: string;
  className?: string;
  normalized?: boolean;
}) {
  return (
    <div
      className={cn(
        "@container relative aspect-square overflow-hidden rounded-md",
        // Реальное фото — на белой фотозоне в обеих темах (белый фон файла не
        // должен выглядеть заплаткой на сером/тёмном); плейсхолдер «Фото
        // готовится» остаётся на обычной фотозоне bg-photo.
        src ? "bg-photo-product" : "bg-photo",
        className,
      )}
    >
      {src ? (
        <Image
          src={src}
          alt={alt}
          fill
          sizes={sizes}
          className={cn("object-contain", normalized ? "" : "p-2")}
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
