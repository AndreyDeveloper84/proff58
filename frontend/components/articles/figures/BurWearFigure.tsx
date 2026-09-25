// Три состояния бура: рабочее и два терминальных. Схема повторяет порядок
// признаков износа из статьи, чтобы её можно было «прочитать» без текста.
type State = {
  title: string;
  note: string;
  tone: "ok" | "bad";
  shank: "sharp" | "worn";
  tip: "whole" | "chipped";
};

const STATES: State[] = [
  {
    title: "Рабочий",
    note: "грани пазов острые, напайка целая",
    tone: "ok",
    shank: "sharp",
    tip: "whole",
  },
  {
    title: "Скруглились пазы",
    note: "проворачивается в патроне — менять сразу",
    tone: "bad",
    shank: "worn",
    tip: "whole",
  },
  {
    title: "Выкрошилась напайка",
    note: "заточке не подлежит, отверстие шире номинала",
    tone: "bad",
    shank: "sharp",
    tip: "chipped",
  },
];

export function BurWearFigure() {
  return (
    <figure className="rounded-md border border-line bg-raised p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {STATES.map((state) => (
          <div key={state.title} className="rounded-sm border border-line bg-surface p-3">
            <svg
              viewBox="0 0 200 70"
              className="h-auto w-full"
              role="img"
              aria-label={`${state.title}: ${state.note}`}
            >
              {/* хвостовик */}
              <rect x="4" y="26" width="72" height="18" rx="3" className="fill-ink-3" opacity="0.5" />
              {state.shank === "sharp" ? (
                <>
                  <rect x="10" y="30" width="40" height="4" rx="2" className="fill-ink" />
                  <rect x="10" y="36" width="40" height="4" rx="2" className="fill-ink" />
                </>
              ) : (
                <>
                  <rect x="10" y="31" width="40" height="2.5" rx="1.2" className="fill-ink" opacity="0.35" />
                  <rect x="10" y="37" width="40" height="2.5" rx="1.2" className="fill-ink" opacity="0.35" />
                </>
              )}

              {/* тело со спиралью */}
              <rect x="76" y="30" width="86" height="10" rx="3" className="fill-ink-3" opacity="0.45" />
              <path
                d="M 80 30 q 10 10 20 0 q 10 10 20 0 q 10 10 20 0 q 10 10 20 0"
                className="fill-none stroke-ink-3"
                strokeWidth="2"
              />

              {/* твердосплавная напайка */}
              {state.tip === "whole" ? (
                <path d="M 162 26 l 26 9 l -26 9 z" className="fill-accent" />
              ) : (
                <path d="M 162 26 l 18 6 l -8 5 l 10 4 l -20 3 z" className="fill-[#d64545]" />
              )}
            </svg>

            <p
              className={`mt-2 text-[12px] font-bold ${
                state.tone === "ok" ? "text-accent" : "text-[#d64545]"
              }`}
            >
              {state.title}
            </p>
            <p className="mt-0.5 text-[11px] leading-[1.4] text-ink-2">{state.note}</p>
          </div>
        ))}
      </div>
      <figcaption className="mt-2 text-[11px] text-ink-3">
        Два правых состояния — повод менять бур, а не «доработать смену».
      </figcaption>
    </figure>
  );
}
