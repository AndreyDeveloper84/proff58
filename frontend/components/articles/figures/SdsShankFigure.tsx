// Схема хвостовиков SDS-plus и SDS-max в едином масштабе (1 мм = 2 px):
// диаметр, глубина посадки в патрон и число пазов — те же цифры, что в тексте
// статьи. Рисуется кодом, поэтому остаётся чёткой на любом экране и весит
// килобайты; цвета берутся из палитры сайта через currentColor.
export function SdsShankFigure() {
  return (
    <figure className="rounded-md border border-line bg-raised p-4">
      <svg
        viewBox="0 0 620 260"
        className="h-auto w-full"
        role="img"
        aria-label="Схема хвостовиков SDS-plus и SDS-max: диаметр 10 и 18 мм, посадка 40 и 90 мм, 4 и 5 пазов"
      >
        <defs>
          <linearGradient id="steel" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#c9d1d6" />
            <stop offset="45%" stopColor="#8e979e" />
            <stop offset="100%" stopColor="#5d666d" />
          </linearGradient>
        </defs>

        {/* --- SDS-plus --- */}
        <text x="0" y="18" className="fill-ink text-[13px] font-bold">
          SDS-plus
        </text>
        <text x="78" y="18" className="fill-ink-3 text-[11px]">
          лёгкие и средние перфораторы, 2–4 кг
        </text>

        {/* стержень: посадка 40 мм → 80 px */}
        <rect x="0" y="40" width="80" height="20" rx="3" fill="url(#steel)" />
        {/* рабочая часть уходит вправо */}
        <rect x="80" y="44" width="150" height="12" rx="2" fill="url(#steel)" opacity="0.55" />
        {/* 2 открытых паза (сквозные, выходят на торец) */}
        <rect x="4" y="44" width="46" height="4" rx="2" fill="#3d454b" />
        <rect x="4" y="52" width="46" height="4" rx="2" fill="#3d454b" />
        {/* 2 закрытых паза (замкнутые ложбинки) */}
        <rect x="56" y="44" width="16" height="4" rx="2" fill="#6d767d" />
        <rect x="56" y="52" width="16" height="4" rx="2" fill="#6d767d" />

        {/* размер посадки */}
        <line x1="0" y1="72" x2="80" y2="72" className="stroke-accent" strokeWidth="1.5" />
        <line x1="0" y1="66" x2="0" y2="78" className="stroke-accent" strokeWidth="1.5" />
        <line x1="80" y1="66" x2="80" y2="78" className="stroke-accent" strokeWidth="1.5" />
        <text x="88" y="76" className="fill-ink-2 text-[11px]">
          посадка в патрон 40 мм
        </text>

        {/* диаметр */}
        <line x1="248" y1="40" x2="248" y2="60" className="stroke-accent" strokeWidth="1.5" />
        <line x1="243" y1="40" x2="253" y2="40" className="stroke-accent" strokeWidth="1.5" />
        <line x1="243" y1="60" x2="253" y2="60" className="stroke-accent" strokeWidth="1.5" />
        <text x="258" y="54" className="fill-ink-2 text-[11px]">
          Ø10 мм · 4 паза
        </text>

        {/* --- SDS-max --- */}
        <text x="0" y="140" className="fill-ink text-[13px] font-bold">
          SDS-max
        </text>
        <text x="76" y="140" className="fill-ink-3 text-[11px]">
          тяжёлые машины от 5 кг, монолит и демонтаж
        </text>

        {/* посадка 90 мм → 180 px, диаметр 18 мм → 36 px */}
        <rect x="0" y="160" width="180" height="36" rx="4" fill="url(#steel)" />
        <rect x="180" y="168" width="120" height="20" rx="3" fill="url(#steel)" opacity="0.55" />
        {/* 3 открытых паза */}
        <rect x="6" y="166" width="104" height="5" rx="2.5" fill="#3d454b" />
        <rect x="6" y="176" width="104" height="5" rx="2.5" fill="#3d454b" />
        <rect x="6" y="186" width="104" height="5" rx="2.5" fill="#3d454b" />
        {/* 2 закрытых паза */}
        <rect x="120" y="170" width="26" height="5" rx="2.5" fill="#6d767d" />
        <rect x="120" y="182" width="26" height="5" rx="2.5" fill="#6d767d" />

        <line x1="0" y1="208" x2="180" y2="208" className="stroke-accent" strokeWidth="1.5" />
        <line x1="0" y1="202" x2="0" y2="214" className="stroke-accent" strokeWidth="1.5" />
        <line x1="180" y1="202" x2="180" y2="214" className="stroke-accent" strokeWidth="1.5" />
        <text x="188" y="212" className="fill-ink-2 text-[11px]">
          посадка в патрон 90 мм
        </text>

        <line x1="318" y1="160" x2="318" y2="196" className="stroke-accent" strokeWidth="1.5" />
        <line x1="313" y1="160" x2="323" y2="160" className="stroke-accent" strokeWidth="1.5" />
        <line x1="313" y1="196" x2="323" y2="196" className="stroke-accent" strokeWidth="1.5" />
        <text x="328" y="182" className="fill-ink-2 text-[11px]">
          Ø18 мм · 5 пазов
        </text>

        {/* легенда — под схемами, чтобы не упираться в правый край кадра */}
        <rect x="0" y="236" width="12" height="6" rx="3" fill="#3d454b" />
        <text x="20" y="243" className="fill-ink-2 text-[11px]">
          открытые пазы — передают вращение
        </text>
        <rect x="250" y="236" width="12" height="6" rx="3" fill="#6d767d" />
        <text x="270" y="243" className="fill-ink-2 text-[11px]">
          закрытые пазы — держат бур в патроне
        </text>
      </svg>
      <figcaption className="mt-2 text-[11px] text-ink-3">
        Хвостовики в едином масштабе: 1 мм чертежа = 2 пикселя.
      </figcaption>
    </figure>
  );
}
