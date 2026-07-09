import { cn } from "@/lib/utils";

// SP2 (#39): многострочное поле (комментарий к заказу, адрес). Токены как у Input.
export function Textarea({
  className,
  invalid,
  ...props
}: React.ComponentProps<"textarea"> & { invalid?: boolean }) {
  return (
    <textarea
      aria-invalid={invalid || undefined}
      className={cn(
        "min-h-20 w-full rounded-md border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        invalid ? "border-danger" : "border-line",
        className,
      )}
      {...props}
    />
  );
}
