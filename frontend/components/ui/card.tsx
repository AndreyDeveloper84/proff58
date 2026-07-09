import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// SP2 (#39): карточка-поверхность. Базовый контейнер для блоков каталога, корзины,
// сводки заказа, форм. Вариант surface/raised — по глубине; padding — по плотности.
const cardVariants = cva("rounded-lg border border-line", {
  variants: {
    surface: {
      base: "bg-surface",
      raised: "bg-raised",
    },
    pad: {
      none: "",
      sm: "p-3",
      md: "p-4",
      lg: "p-6",
    },
  },
  defaultVariants: { surface: "base", pad: "md" },
});

export function Card({
  className,
  surface,
  pad,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof cardVariants>) {
  return <div className={cn(cardVariants({ surface, pad }), className)} {...props} />;
}
