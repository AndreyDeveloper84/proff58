import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// SP2 (#39): индикатор загрузки. Круговой спиннер на текущем цвете (currentColor),
// поэтому наследует цвет родителя (кнопка/состояние). Уважает prefers-reduced-motion.
const spinnerVariants = cva(
  "inline-block animate-spin rounded-full border-current border-t-transparent motion-reduce:animate-none",
  {
    variants: {
      size: {
        sm: "h-4 w-4 border-2",
        md: "h-6 w-6 border-2",
        lg: "h-8 w-8 border-[3px]",
      },
    },
    defaultVariants: { size: "md" },
  },
);

export function Spinner({
  className,
  size,
  label = "Загрузка",
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof spinnerVariants> & { label?: string }) {
  return (
    <span role="status" aria-label={label} className={cn(spinnerVariants({ size }), className)} {...props} />
  );
}
