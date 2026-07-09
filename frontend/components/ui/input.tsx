import { cn } from "@/lib/utils";

// SP2 (#39): базовое текстовое поле. Токены поверхности/границы/текста из globals.css.
// invalid=true подсвечивает ошибку (danger) и ставит aria-invalid для screen-reader.
export function Input({
  className,
  invalid,
  ...props
}: React.ComponentProps<"input"> & { invalid?: boolean }) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(
        "h-9 w-full rounded-md border bg-surface px-3 text-sm text-ink placeholder:text-ink-3",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        invalid ? "border-danger" : "border-line",
        className,
      )}
      {...props}
    />
  );
}
