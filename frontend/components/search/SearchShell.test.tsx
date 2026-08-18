import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// DRF-1166: до этого страница поиска была витриной без ручек — ни фильтров, ни
// сортировки, ни пагинации, а «Найдено» считалось по длине первой страницы (24 из 276).
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/search",
}));

import { SearchShell } from "./SearchShell";
import type { Listing, ListingQuery } from "@/lib/types";

function listing(patch: Partial<Listing> = {}): Listing {
  return {
    category: { title: "Результаты поиска: «дрель»", intro: "", breadcrumb: [] },
    subcategories: [],
    facets: [
      {
        code: "brand",
        label: "Бренд",
        type: "checkbox",
        options: [
          { value: "bosch", label: "Bosch", count: 12, selected: false },
          { value: "makita", label: "Makita", count: 7, selected: false },
        ],
      },
    ],
    sort: [],
    total: 276,
    page: 1,
    perPage: 24,
    products: [],
    ...patch,
  };
}

function query(patch: Partial<ListingQuery> = {}): ListingQuery {
  return {
    category: "",
    page: 1,
    perPage: 24,
    sort: "popular",
    view: "grid",
    filters: {},
    ...patch,
  };
}

describe("SearchShell (DRF-1166)", () => {
  beforeEach(() => replace.mockReset());

  it("счётчик берётся из общего количества, а не из длины страницы", () => {
    render(<SearchShell listing={listing()} query={query()} q="дрель" />);

    expect(screen.getByText("Найдено 276 товаров")).toBeTruthy();
  });

  it("выбор бренда уходит в URL и сохраняет запрос", () => {
    render(<SearchShell listing={listing()} query={query()} q="дрель" />);

    fireEvent.click(screen.getByLabelText(/Bosch/));

    const url = replace.mock.calls[0][0] as string;
    expect(url).toContain("brand=bosch");
    expect(url).toContain("q=%D0%B4%D1%80%D0%B5%D0%BB%D1%8C"); // «дрель»
  });

  it("смена фильтра возвращает на первую страницу", () => {
    render(<SearchShell listing={listing()} query={query({ page: 5 })} q="дрель" />);

    fireEvent.click(screen.getByLabelText(/Makita/));

    const url = replace.mock.calls[0][0] as string;
    expect(url).not.toContain("page=5");
  });

  it("пагинация появляется, когда найденного больше страницы", () => {
    render(<SearchShell listing={listing()} query={query()} q="дрель" />);

    expect(screen.getByLabelText("Пагинация")).toBeTruthy();
  });

  it("пагинации нет, когда всё поместилось на страницу", () => {
    render(<SearchShell listing={listing({ total: 5 })} query={query()} q="дрель" />);

    expect(screen.queryByLabelText("Пагинация")).toBeNull();
  });

  it("сортировка по умолчанию названа релевантностью, а не «по умолчанию»", () => {
    render(<SearchShell listing={listing()} query={query()} q="дрель" />);

    const select = screen.getByLabelText("Сортировка") as HTMLSelectElement;
    expect(select.querySelector("option")?.textContent).toBe("Сначала подходящие");
  });

  it("выбор сортировки уходит в URL", () => {
    render(<SearchShell listing={listing()} query={query()} q="дрель" />);

    fireEvent.change(screen.getByLabelText("Сортировка"), { target: { value: "price_asc" } });

    expect(replace.mock.calls[0][0]).toContain("sort=price_asc");
  });
});
