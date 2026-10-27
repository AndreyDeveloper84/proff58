import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProductDetail } from "@/lib/types";
import { ProductJsonLd } from "./ProductJsonLd";

// Микроразметка товара: sku — артикул из 1С; у товара без артикула поля нет
// (пустой sku поисковику хуже отсутствующего).
function detail(patch: Partial<ProductDetail> = {}): ProductDetail {
  return {
    id: 1,
    slug: "huter-bs-62",
    name: "Бензопила HUTER BS-62",
    brand: "HUTER",
    specs: [],
    price: { final: 9980, currency: "RUB" },
    stock: "in",
    badges: [],
    images: [],
    description: "",
    breadcrumb: [],
    compatible: { accessories: [], crossSell: [], analogs: [], fits: [], compatible: [] },
    ...patch,
  } as ProductDetail;
}

function productLd(d: ProductDetail): Record<string, unknown> {
  const { container } = render(<ProductJsonLd product={d} crumbs={[]} />);
  const [product] = JSON.parse(container.querySelector("script")!.innerHTML);
  return product;
}

describe("ProductJsonLd: sku", () => {
  it("артикул уходит в sku", () => {
    const ld = productLd(detail({ article: "70/6/6" }));
    expect(ld.sku).toBe("70/6/6");
    expect(ld.brand).toEqual({ "@type": "Brand", name: "HUTER" });
  });

  it("без артикула поля sku нет", () => {
    expect(productLd(detail())).not.toHaveProperty("sku");
  });
});
