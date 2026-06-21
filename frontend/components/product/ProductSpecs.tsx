import type { ProductSpec } from "@/lib/types";

export function ProductSpecs({ specs }: { specs: ProductSpec[] }) {
  if (!specs?.length) return null;
  return (
    <p className="line-clamp-1 text-xs text-ink-3">
      {specs.map((s) => s.value).join(" · ")}
    </p>
  );
}
