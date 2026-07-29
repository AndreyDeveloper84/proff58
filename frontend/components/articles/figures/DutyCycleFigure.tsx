// Циферблат десятиминутного цикла сварочного аппарата: ПВ 40 % — четыре минуты
// под дугой и шесть на охлаждение. Сектор считается из процента, поэтому схему
// можно переиспользовать для любого ПВ.
export function DutyCycleFigure({ duty = 40 }: { duty?: number }) {
  const size = 150;
  const r = 62;
  const cx = size / 2;
  const cy = size / 2;
  const angle = (duty / 100) * 360;
  const rad = ((angle - 90) * Math.PI) / 180;
  const x = cx + r * Math.cos(rad);
  const y = cy + r * Math.sin(rad);
  const workMinutes = Math.round(duty / 10);

  return (
    <figure className="flex flex-col items-center gap-4 rounded-md border border-line bg-raised p-4 sm:flex-row sm:items-center sm:gap-6">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="h-[150px] w-[150px] shrink-0"
        role="img"
        aria-label={`Цикл 10 минут: ${workMinutes} минуты работы под нагрузкой и ${10 - workMinutes} минут охлаждения`}
      >
        {/* охлаждение — весь круг фоном */}
        <circle cx={cx} cy={cy} r={r} className="fill-surface stroke-line" strokeWidth="1" />
        {/* работа под нагрузкой — сектор ПВ */}
        <path
          d={`M ${cx} ${cy} L ${cx} ${cy - r} A ${r} ${r} 0 ${angle > 180 ? 1 : 0} 1 ${x} ${y} Z`}
          className="fill-accent"
          opacity="0.9"
        />
        {/* деления по минутам */}
        {Array.from({ length: 10 }, (_, i) => {
          const a = ((i * 36 - 90) * Math.PI) / 180;
          return (
            <line
              key={i}
              x1={cx + (r - 6) * Math.cos(a)}
              y1={cy + (r - 6) * Math.sin(a)}
              x2={cx + r * Math.cos(a)}
              y2={cy + r * Math.sin(a)}
              className="stroke-surface"
              strokeWidth="1.5"
            />
          );
        })}
        <circle cx={cx} cy={cy} r="26" className="fill-raised" />
        <text x={cx} y={cy - 1} textAnchor="middle" className="fill-ink text-[15px] font-bold">
          {duty} %
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" className="fill-ink-3 text-[8px]">
          ПВ
        </text>
      </svg>

      <div className="min-w-0">
        <p className="flex items-center gap-2 text-[13px] text-ink">
          <span className="h-3 w-3 shrink-0 rounded-sm bg-accent" aria-hidden />
          {workMinutes} минуты под дугой
        </p>
        <p className="mt-1.5 flex items-center gap-2 text-[13px] text-ink">
          <span className="h-3 w-3 shrink-0 rounded-sm border border-line bg-surface" aria-hidden />
          {10 - workMinutes} минут на охлаждение
        </p>
        <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">
          Цикл считается за 10 минут. Превысите режим — сработает термозащита и аппарат
          отключится до остывания, посреди шва.
        </p>
      </div>
    </figure>
  );
}
