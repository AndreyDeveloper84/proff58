import { cn } from "@/lib/utils";

// SP2.1 (#474): многострочное поле. Ошибка — через стандартный aria-invalid (ставит Field).
export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
