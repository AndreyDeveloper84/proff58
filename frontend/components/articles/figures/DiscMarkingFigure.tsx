// Разбор маркировки отрезного круга: каждый символ строки A46T BF со своей
// выноской, рядом — схема круга с посадочным 22,23 мм и напоминанием про обороты.
const PARTS = [
  { text: "A", note: "абразив: A — сталь, C — камень и бетон" },
  { text: "46", note: "зернистость: меньше цифра — грубее рез" },
  { text: "T", note: "твёрдость связки: мягкая для нержавейки" },
  { text: "BF", note: "бакелит + стеклосетка (армирование)" },
] as const;

export function DiscMarkingFigure() {
  return (
    <figure className="rounded-md border border-line bg-raised p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-end gap-2">
            {PARTS.map((part) => (
              <span
                key={part.text}
                className="rounded-sm border border-accent/40 bg-surface px-3 py-1.5 font-mono text-[20px] font-bold text-ink"
              >
                {part.text}
              </span>
            ))}
          </div>
          <ul className="mt-3 space-y-1.5">
            {PARTS.map((part) => (
              <li key={part.note} className="flex gap-2 text-[12px] leading-[1.5] text-ink-2">
                <span className="w-9 shrink-0 font-mono font-bold text-accent">{part.text}</span>
                <span className="min-w-0">{part.note}</span>
              </li>
            ))}
          </ul>
        </div>

        <svg
          viewBox="0 0 230 230"
          className="h-[210px] w-[210px] shrink-0 self-center"
          role="img"
          aria-label="Схема отрезного круга: посадочное отверстие 22,23 мм и направление вращения"
        >
          {/* тело круга — тёмный абразив */}
          <circle cx="115" cy="112" r="88" fill="#3a4046" />
          {/* армирующая стеклосетка — пунктир по телу */}
          <circle
            cx="115"
            cy="112"
            r="66"
            fill="none"
            stroke="#5c646b"
            strokeWidth="1.5"
            strokeDasharray="5 5"
          />
          <circle
            cx="115"
            cy="112"
            r="44"
            fill="none"
            stroke="#5c646b"
            strokeWidth="1.5"
            strokeDasharray="5 5"
          />
          {/* фланец и посадочное отверстие */}
          <circle cx="115" cy="112" r="30" fill="#8c949b" />
          <circle cx="115" cy="112" r="17" className="fill-raised" />

          {/* размер посадочного — размерной линией прямо по отверстию */}
          <line x1="98" y1="112" x2="132" y2="112" className="stroke-accent" strokeWidth="1.5" />
          <path d="M 98 112 l 6 -3 v 6 z" className="fill-accent" />
          <path d="M 132 112 l -6 -3 v 6 z" className="fill-accent" />
          <text x="115" y="104" textAnchor="middle" className="fill-ink text-[11px] font-bold">
            22,23
          </text>

          {/* направление вращения */}
          <path
            d="M 55 60 A 80 80 0 0 1 172 58"
            fill="none"
            className="stroke-accent"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <path d="M 172 58 l -11 -5 l 2 -10 z" className="fill-accent" />

          <text x="115" y="221" textAnchor="middle" className="fill-ink-2 text-[12px]">
            125 × 1,2 × 22,23 мм
          </text>
        </svg>
      </div>
      <figcaption className="mt-3 text-[11px] text-ink-3">
        Обороты, указанные на круге, обязаны быть не ниже оборотов вашей УШМ (EN 12413).
      </figcaption>
    </figure>
  );
}
