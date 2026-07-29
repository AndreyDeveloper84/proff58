import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COMPARE_STORAGE_KEY } from "@/lib/compare";
import type { ProductDetail } from "@/lib/types";

vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ add: vi.fn(), cart: null, count: 0 }),
}));

import { CompareTable, buildRows } from "./CompareTable";

function product(slug: string, name: string, specs: [string, string][]): ProductDetail {
  return {
    id: slug.length,
    slug,
    name,
    brand: "Bosch",
    specs: specs.map(([label, value]) => ({ label, value })),
    price: { final: 10000, currency: "RUB" },
    stock: "in",
    badges: [],
    images: [],
    description: "",
    breadcrumb: [],
  };
}

const BOSCH = product("bosch", "Перфоратор Bosch", [
  ["Мощность", "800 Вт"],
  ["Патрон", "SDS-plus"],
  ["Вес", "2,9 кг"],
]);
const MAKITA = product("makita", "Перфоратор Makita", [
  ["Мощность", "780 Вт"],
  ["Патрон", "SDS-plus"],
]);

describe("buildRows", () => {
  it("объединяет характеристики и помечает различия", () => {
    const rows = buildRows([BOSCH, MAKITA]);

    expect(rows.map((r) => r.label)).toEqual(["Мощность", "Патрон", "Вес"]);
    // Значения разные → строка различающаяся.
    expect(rows[0]).toMatchObject({ values: ["800 Вт", "780 Вт"], differs: true });
    // Совпадают → не различающаяся.
    expect(rows[1]).toMatchObject({ values: ["SDS-plus", "SDS-plus"], differs: false });
  });

  // Незаполненная характеристика — тоже различие: у одного вес указан, у другого
  // нет, и человеку это важно увидеть, а не пролистать как «одинаково».
  it("характеристика не у всех товаров считается различием", () => {
    const rows = buildRows([BOSCH, MAKITA]);
    const weight = rows.find((r) => r.label === "Вес")!;

    expect(weight.values).toEqual(["2,9 кг", undefined]);
    expect(weight.differs).toBe(true);
  });
});

describe("CompareTable", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function mockApi(products: ProductDetail[]) {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ products }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;
  }

  it("без выбранных товаров зовёт в каталог, а не показывает пустую таблицу", () => {
    render(<CompareTable />);

    expect(screen.getByText(/В сравнении пока пусто/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("рисует колонку на каждый выбранный товар", async () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["bosch", "makita"]));
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("Перфоратор Bosch")).toBeInTheDocument();
    expect(within(table).getByText("Перфоратор Makita")).toBeInTheDocument();
    expect(within(table).getByText("800 Вт")).toBeInTheDocument();
  });

  // Порядок ответа сервера не гарантирован (четыре параллельных запроса), но
  // колонки обязаны идти в том порядке, в котором человек их добавлял.
  it("держит порядок колонок по порядку добавления", async () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["makita", "bosch"]));
    mockApi([BOSCH, MAKITA]); // сервер ответил в обратном порядке

    render(<CompareTable />);

    const headers = await screen.findAllByRole("columnheader");
    expect(headers[0]).toHaveTextContent("Перфоратор Makita");
    expect(headers[1]).toHaveTextContent("Перфоратор Bosch");
  });

  it("«Только различия» прячет совпадающие строки", async () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["bosch", "makita"]));
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");
    expect(screen.getByText("Патрон")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Только различия/));

    await waitFor(() => expect(screen.queryByText("Патрон")).toBeNull());
    expect(screen.getByText("Мощность")).toBeInTheDocument();
  });

  it("крестик убирает товар из списка", async () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["bosch", "makita"]));
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");

    fireEvent.click(screen.getByLabelText("Убрать Перфоратор Bosch из сравнения"));

    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual(["makita"]),
    );
  });

  // Товар мог быть снят с публикации, пока лежал в списке: страница показывает
  // остальные, а не падает и не висит в загрузке.
  it("переживает товар, который больше не отдаётся", async () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["bosch", "udalyonnyy"]));
    mockApi([BOSCH]);

    render(<CompareTable />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("Перфоратор Bosch")).toBeInTheDocument();
    expect(await screen.findAllByRole("columnheader")).toHaveLength(1); // только живой товар
  });

  it("сбой загрузки показывает ошибку, а не пустой список", async () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["bosch"]));
    global.fetch = vi.fn(async () => new Response("", { status: 500 })) as unknown as typeof fetch;

    render(<CompareTable />);

    expect(await screen.findByText(/Не удалось загрузить/)).toBeInTheDocument();
    expect(screen.queryByText(/В сравнении пока пусто/)).toBeNull();
  });
});
