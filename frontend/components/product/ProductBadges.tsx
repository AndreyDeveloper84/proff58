import { Badge } from "@/components/ui/badge";
import type { BadgeKind } from "@/lib/types";

const LABEL: Record<BadgeKind, { text: string; variant: "hit" | "sale" | "new" }> = {
  hit: { text: "Хит", variant: "hit" },
  sale: { text: "Скидка", variant: "sale" },
  new: { text: "Новинка", variant: "new" },
};

// #574: компонент используется только на PDP (в карточке списка своя разметка),
// где вставлен в обычный поток. Раньше он возвращал `absolute left-2 top-2` без
// позиционированного предка — бейджи выпадали из потока и уезжали в угол окна.
export function ProductBadges({
  badges,
  discountPct,
}: {
  badges: BadgeKind[];
  discountPct?: number;
}) {
  const list = badges ?? [];
  // #574: процент скидки показывался только при бейдже `sale`, хотя discountPct
  // считается всегда (lib/adapters). Товар со старой ценой, но без пометки «Скидка»
  // выглядел как товар без скидки.
  const showDiscount = Boolean(discountPct) && !list.includes("sale");
  if (!list.length && !showDiscount) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {list.map((b) => (
        <Badge key={b} variant={LABEL[b].variant}>
          {b === "sale" && discountPct ? `−${discountPct}%` : LABEL[b].text}
        </Badge>
      ))}
      {showDiscount && <Badge variant="sale">−{discountPct}%</Badge>}
    </div>
  );
}
