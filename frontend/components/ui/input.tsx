import { cn } from "@/lib/utils";

// SP2.1 (#474): базовое текстовое поле. Ошибка подсвечивается через стандартный
// aria-invalid (его ставит Field) — один источник правды для a11y и стиля.
// UX-04: 44 px и 16 px на всех экранах. 16 px — ещё и защита от автоприближения iOS
// при фокусе; прежние 36 px/14 px на desktop покупатели назвали мелкими.
export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-md border border-line bg-surface px-3 text-base text-ink placeholder:text-ink-3",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
