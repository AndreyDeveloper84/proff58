import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PopularBrands } from "./PopularBrands";
import { HOME_CONTENT } from "@/lib/home-content";

// #589: витринный ряд брендов — все ссылки валидны.
describe("PopularBrands (#589)", () => {
  it("показывает все бренды ссылками на поиск", () => {
    render(<PopularBrands />);
    for (const brand of HOME_CONTENT.popularBrands) {
      const link = screen.getByRole("link", { name: `Товары бренда ${brand}` });
      expect(link).toHaveAttribute("href", `/search?q=${encodeURIComponent(brand)}`);
    }
  });
});
