// Шкала крутящего момента: диапазоны в Н·м и задачи, которые они закрывают.
// Ширина сегмента пропорциональна диапазону, поэтому видно, что «универсальные»
// 45–65 Н·м — это узкая полоса, а не половина шкалы.
const BANDS = [
  { from: 0, to: 20, title: "до 20 Н·м", note: "мебель, гипсокартон, мелкий крепёж", opacity: 0.35 },
  { from: 20, to: 45, title: "30–40 Н·м", note: "бытовой ремонт, дерево", opacity: 0.55 },
  { from: 45, to: 65, title: "45–65 Н·м", note: "обрешётка, лаги, длинный саморез", opacity: 0.8 },
  { from: 65, to: 120, title: "от 90 Н·м", note: "интенсивная работа, смесители, ледобур", opacity: 1 },
] as const;

const MAX = 120;
const WIDTH = 600;

export function TorqueScaleFigure() {
  return (
    <figure className="rounded-md border border-line bg-raised p-4">
      <svg
        viewBox="0 0 620 150"
        className="h-auto w-full"
        role="img"
        aria-label="Шкала крутящего момента: до 20, 30–40, 45–65 и от 90 ньютон-метров с задачами"
      >
        {BANDS.map((band) => {
          const x = 10 + (band.from / MAX) * WIDTH;
          const width = ((band.to - band.from) / MAX) * WIDTH;
          return (
            <g key={band.title}>
              <rect
                x={x}
                y="28"
                width={width - 3}
                height="34"
                rx="4"
                className="fill-accent"
                opacity={band.opacity}
              />
              {/* на бледной заливке белая подпись не читается — там берём тёмную */}
              <text
                x={x + 6}
                y="50"
                className={band.opacity < 0.7 ? "fill-ink text-[12px] font-bold" : "fill-surface text-[12px] font-bold"}
              >
                {band.title}
              </text>
            </g>
          );
        })}

        {/* ось */}
        <line x1="10" y1="70" x2="610" y2="70" className="stroke-line" strokeWidth="1.5" />
        {[0, 20, 40, 60, 80, 100, 120].map((value) => {
          const x = 10 + (value / MAX) * WIDTH;
          return (
            <g key={value}>
              <line x1={x} y1="70" x2={x} y2="76" className="stroke-line" strokeWidth="1.5" />
              <text x={x} y="90" textAnchor="middle" className="fill-ink-3 text-[10px]">
                {value}
              </text>
            </g>
          );
        })}
        <text x="610" y="20" textAnchor="end" className="fill-ink-3 text-[11px]">
          крутящий момент, Н·м
        </text>

        {/* подписи задач */}
        {BANDS.map((band, index) => {
          const x = 10 + (band.from / MAX) * WIDTH;
          const y = 108 + (index % 2) * 20;
          return (
            <g key={`${band.title}-note`}>
              <line x1={x + 4} y1="94" x2={x + 4} y2={y - 8} className="stroke-line" strokeWidth="1" />
              <text x={x + 10} y={y} className="fill-ink-2 text-[11px]">
                {band.note}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 text-[11px] text-ink-3">
        Ширина полосы — реальная доля диапазона: «универсальный» участок узкий.
      </figcaption>
    </figure>
  );
}
