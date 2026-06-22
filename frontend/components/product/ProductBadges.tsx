import { Badge } from "@/components/ui/badge";
import type { BadgeKind } from "@/lib/types";

const LABEL: Record<BadgeKind, { text: string; variant: "hit" | "sale" | "new" }> = {
  hit: { text: "Хит", variant: "hit" },
  sale: { text: "Скидка", variant: "sale" },
  new: { text: "Новинка", variant: "new" },
};

export function ProductBadges({
  badges,
  discountPct,
}: {
  badges: BadgeKind[];
  discountPct?: number;
}) {
  if (!badges?.length) return null;
  return (
    <div className="pointer-events-none absolute left-2 top-2 z-10 flex flex-col items-start gap-1">
      {badges.map((b) => (
        <Badge key={b} variant={LABEL[b].variant}>
          {b === "sale" && discountPct ? `−${discountPct}%` : LABEL[b].text}
        </Badge>
      ))}
    </div>
  );
}
