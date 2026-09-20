import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PopularBrands } from "./PopularBrands";
import { HOME_CONTENT } from "@/lib/home-content";

// #589 / UX-07: витринный ряд брендов. Плитки ведут на точную выдачу бренда, а не в
// текстовый поиск — тот находил чужие «аналог Metabo» и терял товары без бренда в названии.
describe("PopularBrands", () => {
  it("каждая плитка ведёт на страницу своего бренда, а не в поиск", () => {
    render(<PopularBrands />);
    for (const brand of HOME_CONTENT.popularBrands) {
      const link = screen.getByRole("link", { name: `Товары бренда ${brand}` });
      const href = link.getAttribute("href") ?? "";
      expect(href).toBe(`/brands/${HOME_CONTENT.popularBrandSlugs[brand]}`);
      expect(href).not.toContain("/search");
    }
  });

  it("Metabo открывает /brands/metabo", () => {
    render(<PopularBrands />);
    expect(screen.getByRole("link", { name: "Товары бренда Metabo" })).toHaveAttribute(
      "href",
      "/brands/metabo",
    );
  });

  it("slug заморожен для каждого бренда списка и не выводится из регистра", () => {
    for (const brand of HOME_CONTENT.popularBrands) {
      expect(HOME_CONTENT.popularBrandSlugs[brand]).toMatch(/^[a-z0-9-]+$/);
    }
    // Кириллица: toLowerCase дал бы «ресанта», backend ждёт транслит.
    expect(HOME_CONTENT.popularBrandSlugs["Ресанта"]).toBe("resanta");
  });
});
