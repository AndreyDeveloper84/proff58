import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        accent: "bg-accent text-accent-ink hover:brightness-95",
        outline: "border border-line bg-surface text-ink hover:bg-raised",
        ghost: "text-ink-2 hover:bg-raised hover:text-ink",
      },
      // #474/#478: mobile touch-target. default 44px; primary CTA (lg) 48px;
      // sm визуально компактнее, но hit-area ≥44px на мобиле (min-h-11); desktop 36–40px.
      size: {
        default: "h-11 px-4 sm:h-9",
        lg: "h-12 px-6 text-base sm:h-11",
        sm: "min-h-11 px-3 sm:min-h-0 sm:h-8",
        icon: "h-11 w-11 sm:h-9 sm:w-9",
      },
    },
    defaultVariants: { variant: "accent", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}

export { buttonVariants };
