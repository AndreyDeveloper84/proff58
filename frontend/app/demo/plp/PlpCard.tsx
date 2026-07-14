import { Clock, Heart, ShoppingCart, Wrench } from "lucide-react";

import { cn } from "@/lib/utils";

import type { PlpProduct, PlpStock } from "./mocks";

const money = (v: number) => v.toLocaleString("ru-RU") + " ₽";

// Конфиг статус-лейбла карточки (цвет+текст) — точно по макету.
const STATUS: Record<PlpStock, { label: string; cls: string; dot?: boolean; icon?: boolean }> = {
  in: { label: "В наличии", cls: "text-brand", dot: true },
  low: { label: "Мало осталось", cls: "text-rating", dot: true },
  order: { label: "Под заказ", cls: "text-st-confirm", icon: true },
  out: { label: "Нет в наличии", cls: "text-danger", dot: true },
  no_price: { label: "Цена уточняется", cls: "text-ink-3", dot: true },
};

function StatusLabel({ stock }: { stock: PlpStock }) {
  const s = STATUS[stock];
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-semibold", s.cls)}>
      {s.icon ? (
        <Clock className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      )}
      {s.label}
    </span>
  );
}

// CTA карточки зависит от статуса (В корзину / Под заказ / Сообщить / Уточнить).
function CardCta({ stock }: { stock: PlpStock }) {
  if (stock === "in" || stock === "low") {
    return (
      <button className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-semibold text-white transition-colors hover:brightness-95 sm:h-10">
        <ShoppingCart className="h-4 w-4" aria-hidden />В корзину
      </button>
    );
  }
  const label =
    stock === "order" ? "Под заказ" : stock === "out" ? "Сообщить о поступлении" : "Уточнить цену";
  return (
    <button className="inline-flex h-11 items-center justify-center rounded-md border border-line px-4 text-sm font-medium text-ink-2 transition-colors hover:bg-raised sm:h-10">
      {label}
    </button>
  );
}

export function PlpCard({ p }: { p: PlpProduct }) {
  const dimmed = p.stock === "out";
  return (
    <article
      className={cn(
        "group flex flex-col rounded-lg border border-line bg-surface p-3 transition-shadow hover:shadow-sm",
        dimmed && "opacity-70",
      )}
    >
      {/* Верх: статус + сердечко */}
      <div className="mb-2 flex items-start justify-between">
        <StatusLabel stock={p.stock} />
        <button
          aria-label="В избранное"
          className="grid h-11 w-11 place-items-center rounded-full text-ink-3 transition-colors hover:text-brand sm:h-8 sm:w-8"
        >
          <Heart className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {/* Фото / placeholder + бейдж скидки */}
      <div className="relative mb-3 aspect-square overflow-hidden rounded-md bg-photo">
        {p.discountPct != null && (
          <span className="absolute left-2 top-2 rounded-md bg-danger px-1.5 py-0.5 text-[11px] font-bold text-white">
            −{p.discountPct}%
          </span>
        )}
        {p.noPhoto ? (
          <div className="grid h-full w-full place-items-center text-photo-ink">
            <Wrench className="h-12 w-12" aria-hidden strokeWidth={1.25} />
          </div>
        ) : (
          // Фото товара — плейсхолдер-иллюстрация (в проде — реальное фото).
          <div className="grid h-full w-full place-items-center">
            <Wrench className="h-16 w-16 text-photo-ink/40" aria-hidden strokeWidth={1} />
          </div>
        )}
      </div>

      {/* Бренд → название → ТТХ */}
      <p className="text-xs text-ink-3">{p.brand}</p>
      <h3 className="mt-0.5 line-clamp-2 text-sm font-medium text-ink">{p.name}</h3>
      <p className="mt-1 line-clamp-1 text-xs text-ink-2">{p.specs}</p>

      {/* Цена */}
      <div className="mt-2 flex min-h-7 items-baseline gap-2">
        {p.price != null ? (
          <>
            <span className="text-lg font-bold text-ink">{money(p.price)}</span>
            {p.oldPrice != null && (
              <span className="text-xs text-ink-3 line-through">{money(p.oldPrice)}</span>
            )}
          </>
        ) : (
          <span className="text-sm text-ink-3">Цена уточняется</span>
        )}
      </div>

      {/* CTA */}
      <div className="mt-3">
        <CardCta stock={p.stock} />
      </div>
    </article>
  );
}
