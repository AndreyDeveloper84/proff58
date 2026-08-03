import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Карточка тянет корзину через контекст — блоку витрины она не интересна.
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ count: 0, add: vi.fn(), items: [] }),
}));

import type { Product } from "@/lib/types";
import { Bestsellers } from "./Bestsellers";

const PRODUCT: Product = {
  id: 1,
  name: "Перфоратор",
  slug: "perforator",
  brand: "Bosch",
  category: { name: "Электроинструмент", slug: "elektroinstrument" },
  price: { final: 5000, currency: "RUB" },
  stock: "in_stock",
  badges: ["hit"],
  image: null,
  specs: [],
};

describe("Bestsellers", () => {
  it("реальные продажи — блок называется «Хиты продаж»", () => {
    render(<Bestsellers products={[PRODUCT]} kind="bestsellers" />);

    expect(screen.getByRole("heading", { name: "Хиты продаж" })).toBeInTheDocument();
  });

  // Пока продаж нет, блок обязан признаться, что показывает новинки: называть
  // их хитами — та самая неправда витрины, ради которой всё и затевалось.
  it("продаж нет — блок называется «Новинки каталога»", () => {
    render(<Bestsellers products={[PRODUCT]} kind="new" />);

    expect(screen.getByRole("heading", { name: "Новинки каталога" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Хиты продаж" })).toBeNull();
  });

  it("без товаров блок не рендерится", () => {
    const { container } = render(<Bestsellers products={[]} kind="bestsellers" />);

    expect(container).toBeEmptyDOMElement();
  });
});
