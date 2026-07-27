import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PopularBrands } from "./PopularBrands";
import { PopularCategories } from "./PopularCategories";
import { HOME_CONTENT } from "@/lib/home-content";

// #589: витринные ряды — категории-pill'ы и бренды, все ссылки валидны.
describe("PopularBrands (#589)", () => {
  it("показывает все бренды ссылками на поиск", () => {
    render(<PopularBrands />);
    for (const brand of HOME_CONTENT.popularBrands) {
      const link = screen.getByRole("link", { name: `Товары бренда ${brand}` });
      expect(link).toHaveAttribute("href", `/search?q=${encodeURIComponent(brand)}`);
    }
  });
});

describe("PopularCategories (#589)", () => {
  const cats = [
    { id: 1, name: "Электроинструмент", slug: "elektroinstrument", children: [] },
    { id: 2, name: "Ручной инструмент", slug: "ruchnoy-instrument", children: [] },
  ];

  it("pill-ссылки ведут в разделы каталога + «Ещё категории»", () => {
    render(<PopularCategories categories={cats} />);
    expect(screen.getByRole("link", { name: "Электроинструмент" })).toHaveAttribute(
      "href",
      "/catalog/elektroinstrument",
    );
    expect(screen.getByRole("link", { name: /Ещё категории/ })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  it("пустой список категорий не рендерит блок", () => {
    const { container } = render(<PopularCategories categories={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
