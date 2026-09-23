import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COMPARE_STORAGE_KEY, removeFromCompare, toggleCompare } from "@/lib/compare";
import type { ProductDetail } from "@/lib/types";

vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ add: vi.fn(), cart: null, count: 0 }),
}));

import { CompareTable, buildGroups, buildRows, commonSection } from "./CompareTable";

function product(
  slug: string,
  name: string,
  specs: [string, string][],
  breadcrumb: { name: string; slug: string }[] = [],
): ProductDetail {
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
    breadcrumb,
    seoIndexable: true,
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

const PERF = [
  { name: "Электроинструмент", slug: "ei" },
  { name: "Перфораторы", slug: "perforatory" },
];

describe("buildGroups", () => {
  it("раскладывает строки по разделам паспорта и не создаёт пустых разделов", () => {
    const groups = buildGroups([
      product("a", "A", [
        ["Мощность", "800 Вт"],
        ["Вес", "2,9 кг"],
        ["Цвет", "Синий"],
      ]),
      product("b", "B", [
        ["Мощность", "780 Вт"],
        ["Цвет", "Синий"],
      ]),
    ]);

    // «Оснастки» нет ни у одного товара — раздела тоже нет.
    expect(groups.map((g) => g.title)).toEqual([
      "Производительность",
      "Питание и корпус",
      "Дополнительно",
    ]);
    expect(groups[0].rows.map((r) => r.label)).toEqual(["Мощность"]);
    expect(groups[2].rows[0]).toMatchObject({ label: "Цвет", differs: false });
  });

  it("не оставляет строку, пустую у всех товаров", () => {
    const rows = buildRows([
      product("a", "A", [["Мощность", "800 Вт"], ["Напряжение", " "]]),
      product("b", "B", [["Мощность", "800 Вт"], ["Напряжение", ""]]),
    ]);

    expect(rows.map((r) => r.label)).toEqual(["Мощность"]);
  });
});

describe("commonSection", () => {
  it("берёт самый глубокий общий раздел", () => {
    const a = product("a", "A", [], PERF);
    const b = product("b", "B", [], [PERF[0], { name: "Дрели", slug: "dreli" }]);

    expect(commonSection([a, a])).toEqual(PERF[1]);
    expect(commonSection([a, b])).toEqual(PERF[0]);
    expect(commonSection([a, product("c", "C", [], [{ name: "Сад", slug: "sad" }])])).toBeNull();
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

  function requested(input: RequestInfo | URL): string[] {
    const url = new URL(String(input), "http://localhost");
    return (url.searchParams.get("slugs") ?? "").split(",").filter(Boolean);
  }

  function json(products: ProductDetail[]): Response {
    return new Response(JSON.stringify({ products }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }

  // Сервер отдаёт только запрошенные товары и в своём порядке (порядке `products`),
  // а не в порядке запроса.
  function mockApi(products: ProductDetail[]) {
    const fn = vi.fn(async (input: RequestInfo | URL) => {
      const slugs = requested(input);
      return json(products.filter((p) => slugs.includes(p.slug)));
    });
    global.fetch = fn as unknown as typeof fetch;
    return fn;
  }

  // Ответ сервера по команде теста: так воспроизводятся гонки «удалили, пока
  // шёл запрос».
  function mockDeferredApi() {
    const calls: {
      slugs: string[];
      signal?: AbortSignal;
      resolve: (products: ProductDetail[]) => void;
    }[] = [];
    global.fetch = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          calls.push({
            slugs: requested(input),
            signal: init?.signal ?? undefined,
            resolve: (products) => resolve(json(products)),
          });
        }),
    ) as unknown as typeof fetch;
    return calls;
  }

  function select(...slugs: string[]) {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(slugs));
  }

  it("без выбранных товаров зовёт в каталог, а не показывает пустую таблицу", () => {
    render(<CompareTable />);

    expect(screen.getByText(/В сравнении пока пусто/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("рисует колонку на каждый выбранный товар", async () => {
    select("bosch", "makita");
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
    select("makita", "bosch");
    mockApi([BOSCH, MAKITA]); // сервер ответил в обратном порядке

    render(<CompareTable />);

    const headers = await screen.findAllByRole("columnheader");
    expect(headers[0]).toHaveTextContent("Перфоратор Makita");
    expect(headers[1]).toHaveTextContent("Перфоратор Bosch");
  });

  it("группирует характеристики отдельными tbody с заголовком раздела", async () => {
    select("bosch", "makita");
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");

    const perf = screen.getByText("Производительность").closest("th")!;
    expect(perf).toHaveAttribute("scope", "rowgroup");
    const body = perf.closest("tbody")!;
    expect(within(body).getByText("Мощность")).toBeInTheDocument();
    expect(within(body).queryByText("Патрон")).toBeNull();
    expect(screen.getByText("Патрон").closest("tbody")).toHaveTextContent("Оснастка");
    // Разделов без данных нет.
    expect(screen.queryByText("Дополнительно")).toBeNull();
  });

  it("«Только различия» прячет совпадающие строки и опустевшие разделы", async () => {
    select("bosch", "makita");
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");
    expect(screen.getByText("Патрон")).toBeInTheDocument();
    expect(screen.getByText("Оснастка")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Только различия/));

    await waitFor(() => expect(screen.queryByText("Патрон")).toBeNull());
    // В «Оснастке» была только совпадающая строка — раздел скрыт целиком.
    expect(screen.queryByText("Оснастка")).toBeNull();
    expect(screen.getByText("Мощность")).toBeInTheDocument();
    expect(screen.getByText("Вес")).toBeInTheDocument();
  });

  it("различие отмечено у названия и доступно скринридеру, без заливки", async () => {
    select("bosch", "makita");
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");

    const power = screen.getByRole("rowheader", { name: /Мощность/ });
    expect(power).toHaveTextContent("значения различаются");
    expect(screen.getByRole("rowheader", { name: "Патрон" })).not.toHaveTextContent(
      "различаются",
    );
    expect(screen.getByText("800 Вт").className).toContain("font-semibold");
    expect(screen.getByText("800 Вт").className).not.toMatch(/bg-accent/);
  });

  it("крестик убирает товар из списка и колонку сразу, без перезапроса", async () => {
    select("bosch", "makita");
    const api = mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");

    fireEvent.click(screen.getByLabelText("Убрать Перфоратор Bosch из сравнения"));

    expect(JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual(["makita"]);
    expect(screen.getAllByRole("columnheader")).toHaveLength(1);
    expect(screen.queryByText("Перфоратор Bosch")).toBeNull();
    expect(api).toHaveBeenCalledTimes(1);
  });

  it("убранный и снова добавленный товар загружается заново — без старой цены", async () => {
    select("bosch", "makita");
    const api = mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByText("Перфоратор Makita");

    fireEvent.click(screen.getByLabelText("Убрать Перфоратор Makita из сравнения"));
    act(() => {
      toggleCompare("makita");
    });

    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    expect(requested(api.mock.calls[1][0])).toEqual(["makita"]);
    expect(await screen.findByText("Перфоратор Makita")).toBeInTheDocument();
  });

  it("добавленный товар догружается один, таблица не мигает загрузкой", async () => {
    select("bosch");
    const api = mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByText("Перфоратор Bosch");

    act(() => {
      toggleCompare("makita");
    });

    // Пока Makita в пути, Bosch остаётся на месте.
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(await screen.findByText("Перфоратор Makita")).toBeInTheDocument();
    expect(api).toHaveBeenCalledTimes(2);
    expect(requested(api.mock.calls[1][0])).toEqual(["makita"]);
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
  });

  it("поздний ответ не возвращает товар, удалённый во время загрузки", async () => {
    select("bosch", "makita");
    const calls = mockDeferredApi();

    render(<CompareTable />);
    expect(screen.getByText(/Загружаем товары/)).toBeInTheDocument();
    expect(calls).toHaveLength(1);

    act(() => removeFromCompare("makita"));

    // Прежний запрос отменён, ушёл новый — только за оставшимся товаром.
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[0].signal?.aborted).toBe(true);
    expect(calls[1].slugs).toEqual(["bosch"]);

    // Старый ответ приходит последним и с удалённым товаром внутри.
    await act(async () => {
      calls[1].resolve([BOSCH]);
      calls[0].resolve([BOSCH, MAKITA]);
    });

    expect(await screen.findByText("Перфоратор Bosch")).toBeInTheDocument();
    expect(screen.queryByText("Перфоратор Makita")).toBeNull();
    expect(screen.getAllByRole("columnheader")).toHaveLength(1);
  });

  // Товар мог быть снят с публикации, пока лежал в списке: страница показывает
  // остальные, а не падает и не висит в загрузке.
  it("переживает товар, который больше не отдаётся", async () => {
    select("bosch", "udalyonnyy");
    const api = mockApi([BOSCH]);

    render(<CompareTable />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("Перфоратор Bosch")).toBeInTheDocument();
    expect(await screen.findAllByRole("columnheader")).toHaveLength(1); // только живой товар
    expect(screen.getByText(/больше не продаётся/)).toBeInTheDocument();
    expect(screen.queryByText(/Загружаем/)).toBeNull();
    // Отметка «нет такого» кэшируется — повторных запросов по кругу нет.
    expect(api).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Убрать из списка" }));
    expect(JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual(["bosch"]);
  });

  it("если не отдан ни один товар — пустое состояние, а не вечная загрузка", async () => {
    select("udalyonnyy");
    mockApi([]);

    render(<CompareTable />);

    expect(await screen.findByText(/больше не продаются/)).toBeInTheDocument();
    expect(screen.queryByText(/Загружаем/)).toBeNull();
  });

  it("«Добавить товар» ведёт в общий раздел сравниваемых товаров", async () => {
    select("bosch", "makita");
    mockApi([
      product("bosch", "Перфоратор Bosch", [["Мощность", "800 Вт"]], PERF),
      product("makita", "Перфоратор Makita", [["Мощность", "780 Вт"]], PERF),
    ]);

    render(<CompareTable />);
    await screen.findByRole("table");

    const link = screen.getByRole("link", {
      name: "Добавить товар из раздела «Перфораторы»",
    });
    expect(link).toHaveAttribute("href", "/catalog/perforatory");
  });

  it("без общего раздела «Добавить товар» ведёт в каталог", async () => {
    select("bosch", "makita");
    mockApi([BOSCH, MAKITA]);

    render(<CompareTable />);
    await screen.findByRole("table");

    expect(screen.getByRole("link", { name: "Добавить товар" })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  it("сбой загрузки показывает ошибку и даёт повторить", async () => {
    select("bosch");
    global.fetch = vi.fn(async () => new Response("", { status: 500 })) as unknown as typeof fetch;

    render(<CompareTable />);

    expect(await screen.findByText(/Не удалось загрузить/)).toBeInTheDocument();
    expect(screen.queryByText(/В сравнении пока пусто/)).toBeNull();

    mockApi([BOSCH]);
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Перфоратор Bosch")).toBeInTheDocument();
  });
});
