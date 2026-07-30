// Режим хранения Li-Ion: окно заряда 40–60 % и температурная шкала с тем, во
// сколько раз ускоряется деградация. Цифры — те же, что в тексте статьи.
const TEMPERATURES = [
  { label: "15–25 °C", note: "норма хранения", tone: "ok" },
  { label: "25 °C", note: "умеренная деградация", tone: "ok" },
  { label: "40 °C", note: "быстрее в 2–3 раза", tone: "warn" },
  { label: "60 °C", note: "ресурс меньше в 10 раз", tone: "bad" },
] as const;

const TONE_CLASS = {
  ok: "bg-accent",
  warn: "bg-[#e0a800]",
  bad: "bg-[#d64545]",
} as const;

export function BatteryStorageFigure() {
  return (
    <figure className="rounded-md border border-line bg-raised p-4">
      <svg
        viewBox="0 0 620 130"
        className="h-auto w-full"
        role="img"
        aria-label="Шкала заряда: рекомендованное окно хранения 40–60 процентов"
      >
        {/* корпус батареи */}
        <rect
          x="10"
          y="34"
          width="560"
          height="46"
          rx="6"
          className="fill-surface stroke-line"
          strokeWidth="2"
        />
        <rect x="574" y="48" width="12" height="18" rx="3" className="fill-line" />

        {/* «опасные» края — глубокий разряд и постоянные 100 % */}
        <rect x="14" y="38" width="212" height="38" rx="4" className="fill-ink-3" opacity="0.12" />
        <rect x="352" y="38" width="214" height="38" rx="4" className="fill-ink-3" opacity="0.12" />
        {/* рабочее окно 40–60 % */}
        <rect x="226" y="38" width="126" height="38" rx="4" className="fill-accent" opacity="0.9" />
        <text x="289" y="62" textAnchor="middle" className="fill-surface text-[14px] font-bold">
          40–60 %
        </text>

        {/* деления */}
        {[0, 20, 40, 60, 80, 100].map((percent) => {
          const x = 14 + (percent / 100) * 552;
          return (
            <g key={percent}>
              <line x1={x} y1="84" x2={x} y2="92" className="stroke-line" strokeWidth="1.5" />
              <text x={x} y="106" textAnchor="middle" className="fill-ink-3 text-[10px]">
                {percent} %
              </text>
            </g>
          );
        })}

        <text x="14" y="24" className="fill-ink-2 text-[11px]">
          глубокий разряд — батарея может не «проснуться»
        </text>
        <text x="566" y="24" textAnchor="end" className="fill-ink-2 text-[11px]">
          хранение под 100 % ускоряет старение
        </text>
      </svg>

      <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
        {TEMPERATURES.map((item) => (
          <li key={item.label} className="flex items-center gap-2 text-[12px] text-ink-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${TONE_CLASS[item.tone]}`} aria-hidden />
            <span className="font-semibold text-ink">{item.label}</span>
            <span>— {item.note}</span>
          </li>
        ))}
      </ul>
      <figcaption className="mt-2 text-[11px] text-ink-3">
        Окно хранения и цена перегрева: жара сокращает ресурс быстрее, чем работа.
      </figcaption>
    </figure>
  );
}
