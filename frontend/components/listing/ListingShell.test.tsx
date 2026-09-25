import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Состояние «тип выбран» (DRF-994): панели типов нет, вместо неё возврат к списку,
// чипа «Тип: X» нет — он повторял строку возврата и накручивал счётчик «Фильтры».
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/catalog/elektroinstrument",
}));
vi.mock("@/lib/analytics", () => ({ track: vi.fn() }));

import { ListingShell } from "./ListingShell";
import type { Listing, ListingQuery } from "@/lib/types";

function listing(patch: Partial<Listing> = {}): Listing {
  return {
    category: { title: "Электроинструмент", intro: "", breadcrumb: [] },
    subcategories: [],
    facets: [
      {
        code: "tool_type",
        label: "Тип инструмента",
        type: "checkbox",
        isNav: true,
        kind: "nav",
        options: [
          { value: "gravery", label: "Граверы", count: 12, selected: false },
          { value: "dreli", label: "Дрели и шуруповёрты", count: 337, selected: false },
          { value: "pily", label: "Пилы", count: 150, selected: false },
        ],
      },
    ],
    sort: [],
    total: 12,
    page: 1,
    perPage: 24,
    products: [],
    ...patch,
  };
}

function query(patch: Partial<ListingQuery> = {}): ListingQuery {
  return {
    category: "elektroinstrument",
    page: 1,
    perPage: 24,
    sort: "popular",
    view: "grid",
    filters: {},
    ...patch,
  };
}

beforeEach(() => replace.mockReset());

describe("ListingShell: тип выбран", () => {
  it("панель типов исчезает, остаётся возврат к списку", () => {
    render(<ListingShell listing={listing()} query={query({ toolType: "gravery" })} />);

    expect(screen.getByRole("button", { name: /Все виды электроинструмента/ })).toBeInTheDocument();
    // Ни одной капсулы прочих типов: выбор уже сделан.
    expect(screen.queryByRole("button", { name: /Дрели и шуруповёрты/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Пилы/ })).not.toBeInTheDocument();
  });

  it("чипа «Тип: Граверы» нет", () => {
    render(<ListingShell listing={listing()} query={query({ toolType: "gravery" })} />);

    expect(screen.queryByText(/Тип: Граверы/)).not.toBeInTheDocument();
  });

  // Счётчик на кнопке «Фильтры» считает чипы: пока тип был чипом, страница типа
  // выглядела как страница с одним применённым фильтром.
  it("счётчик «Фильтры» тип не учитывает", () => {
    render(<ListingShell listing={listing()} query={query({ toolType: "gravery" })} />);

    const filters = screen.getByRole("button", { name: /Фильтры/ });
    expect(filters.textContent).toBe("Фильтры");
  });

  it("возврат снимает тип и сохраняет сортировку, вид и размер страницы", () => {
    render(
      <ListingShell
        listing={listing()}
        query={query({ toolType: "gravery", sort: "price_asc", view: "list", perPage: 48 })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Все виды электроинструмента/ }));

    const url = replace.mock.calls.at(-1)?.[0] as string;
    expect(url).not.toContain("tool_type");
    expect(url).toContain("sort=price_asc");
    expect(url).toContain("view=list");
    expect(url).toContain("per_page=48");
  });

  it("без выбранного типа возврата нет, панель на месте", () => {
    render(<ListingShell listing={listing()} query={query()} />);

    expect(screen.queryByRole("button", { name: /Все виды/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Дрели и шуруповёрты/ })).toBeInTheDocument();
  });
});
