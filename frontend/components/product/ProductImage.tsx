import Image from "next/image";

export function ProductImage({ src, alt }: { src?: string; alt: string }) {
  return (
    <div className="relative aspect-square overflow-hidden rounded-md bg-raised">
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
        <div className="flex h-full items-center justify-center text-xs text-ink-3">
          Нет фото
        </div>
      )}
    </div>
  );
}
