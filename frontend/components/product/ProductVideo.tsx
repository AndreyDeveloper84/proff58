import type { JSX } from "react";

// Извлекает id ролика из разных форм YouTube-URL (watch?v=, youtu.be, embed).
function youtubeId(url: string): string | null {
  const patterns = [
    /[?&]v=([\w-]{11})/,
    /youtu\.be\/([\w-]{11})/,
    /youtube\.com\/embed\/([\w-]{11})/,
  ];
  for (const re of patterns) {
    const m = url.match(re);
    if (m) return m[1];
  }
  return null;
}

// Блок видео о товаре: адаптивный YouTube-embed. Пустой/невалидный URL → ничего.
export function ProductVideo({ url }: { url?: string }): JSX.Element | null {
  if (!url) return null;
  const id = youtubeId(url);
  if (!id) return null;
  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-line">
      <iframe
        src={`https://www.youtube.com/embed/${id}`}
        title="Видео о товаре"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className="absolute inset-0 h-full w-full"
      />
    </div>
  );
}
