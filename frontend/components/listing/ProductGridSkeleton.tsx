// Скелетон карточек на время навигации (useTransition) — без full-page spinner (§15).
// Чисто презентационный, aria-hidden: для скринридеров «занятость» сообщает aria-busy выдачи.

type Props = { view?: "grid" | "list"; count?: number };

export function ProductGridSkeleton({ view = "grid", count = 12 }: Props) {
  const cards = Array.from({ length: Math.max(1, count) });
  if (view === "list") {
    return (
      <div className="flex flex-col gap-3" aria-hidden>
        {cards.map((_, i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-line bg-raised"
          />
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6" aria-hidden>
      {cards.map((_, i) => (
        <div
          key={i}
          className="h-64 animate-pulse rounded-lg border border-line bg-raised"
        />
      ))}
    </div>
  );
}
