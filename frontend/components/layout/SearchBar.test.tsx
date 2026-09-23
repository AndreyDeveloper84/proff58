import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Быстрый поиск в шапке: combobox (WAI-ARIA 1.2) поверх BFF /api/search/quick.
const nav = vi.hoisted(() => ({ push: vi.fn(), pathname: "/" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
  usePathname: () => nav.pathname,
}));

import { SearchBar } from "./SearchBar";

const RESULT = {
  query: "шуруп",
  categories: [
    { name: "Шурупы", category: { name: "Крепёж", slug: "krepezh" }, tool_type: "shurupy" },
    { name: "Перфораторы", category: { name: "Перфораторы", slug: "perf" }, tool_type: null },
  ],
  products: [
    {
      id: 7,
      name: "Шуруповёрт аккумуляторный Makita DF333DWYE",
      card_name: "Шуруповёрт Makita DF333",
      slug: "makita-df333",
      brand: "Makita",
      price: "5990.00",
      currency: "RUB",
      stock_status: "in_stock",
      main_image: null,
      attributes: [],
    },
  ],
};

const EMPTY = { query: "шуруп", categories: [], products: [] };

const fetchMock = vi.fn();

function respond(body: unknown, ok = true) {
  // Не mockReset + reject: такой мок в этом проекте даёт ложный unhandled rejection.
  fetchMock.mockImplementation(() =>
    Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) }),
  );
}

function input() {
  return screen.getByRole("combobox", { name: "Поиск товаров" });
}

function type(value: string) {
  fireEvent.change(input(), { target: { value } });
}

// Дождаться debounce и ответа fetch (микрозадачи) под fake timers.
async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
}

async function search(value = "шуруп") {
  render(<SearchBar />);
  fireEvent.focus(input());
  type(value);
  await settle();
}

describe("SearchBar: быстрый поиск", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
    nav.push.mockClear();
    nav.pathname = "/";
    respond(RESULT);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("серия нажатий — один запрос после паузы", async () => {
    render(<SearchBar />);
    for (const value of ["шу", "шур", "шуру", "шуруп"]) {
      type(value);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
    }
    expect(fetchMock).not.toHaveBeenCalled();
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/search/quick?q=${encodeURIComponent("шуруп")}`);
  });

  it("короткий запрос не ищет и не открывает панель", async () => {
    await search("ш");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(input()).toHaveAttribute("aria-expanded", "false");
  });

  it("повтор того же текста берётся из кэша без запроса", async () => {
    await search("шуруп");
    type("шуру");
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // Регистр и пробелы по краям — тот же ключ кэша.
    type(" ШУРУП ");
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("option", { name: /Шурупы/ })).toBeInTheDocument();
  });

  it("показывает разделы и товары, ссылка раздела несёт tool_type", async () => {
    await search();
    const listbox = screen.getByRole("listbox");
    const sections = within(listbox).getByRole("group", { name: "Разделы" });
    const products = within(listbox).getByRole("group", { name: "Товары" });

    // Вид товара подписан разделом второй строкой; раздел без вида — одной строкой.
    const screws = within(sections).getByRole("option", { name: /Шурупы/ });
    expect(screws).toHaveTextContent("Крепёж");
    const perf = within(sections).getByRole("option", { name: /Перфораторы/ });
    expect(perf.textContent).toBe("Перфораторы");

    const product = within(products).getByRole("option", { name: /Makita DF333/ });
    expect(product).toHaveTextContent("Makita");
    expect(product).toHaveTextContent(/5\s990/);
    expect(product).toHaveTextContent("В наличии");

    fireEvent.click(screws);
    expect(nav.push).toHaveBeenCalledWith("/catalog/krepezh?tool_type=shurupy");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("раздел без вида ведёт в категорию без фильтра", async () => {
    await search();
    fireEvent.click(screen.getByRole("option", { name: "Перфораторы" }));
    expect(nav.push).toHaveBeenCalledWith("/catalog/perf");
  });

  it("стрелки двигают активную опцию, Enter выбирает её", async () => {
    await search();
    const field = input();
    expect(field).not.toHaveAttribute("aria-activedescendant");

    fireEvent.keyDown(field, { key: "ArrowDown" });
    const first = screen.getByRole("option", { name: /Шурупы/ });
    expect(field).toHaveAttribute("aria-activedescendant", first.id);
    expect(first).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(field, { key: "ArrowDown" });
    fireEvent.keyDown(field, { key: "ArrowDown" });
    const product = screen.getByRole("option", { name: /Makita DF333/ });
    expect(field).toHaveAttribute("aria-activedescendant", product.id);

    fireEvent.keyDown(field, { key: "Enter" });
    expect(nav.push).toHaveBeenCalledWith("/product/makita-df333");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("стрелка вверх идёт по кругу на «Все результаты»", async () => {
    await search();
    fireEvent.keyDown(input(), { key: "ArrowUp" });
    const all = screen.getByRole("option", { name: "Все результаты по запросу «шуруп»" });
    expect(input()).toHaveAttribute("aria-activedescendant", all.id);
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    expect(input()).toHaveAttribute(
      "aria-activedescendant",
      screen.getByRole("option", { name: /Шурупы/ }).id,
    );
  });

  it("Enter без активной опции — обычный переход на страницу поиска", async () => {
    await search();
    fireEvent.submit(input().closest("form")!);
    expect(nav.push).toHaveBeenCalledWith(`/search?q=${encodeURIComponent("шуруп")}`);
  });

  it("Esc закрывает панель и не очищает поле", async () => {
    await search();
    const notPrevented = fireEvent.keyDown(input(), { key: "Escape" });
    expect(notPrevented).toBe(false);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(input()).toHaveValue("шуруп");
    expect(input()).toHaveAttribute("aria-expanded", "false");
  });

  it("Esc до ответа отменяет отложенный запрос", async () => {
    render(<SearchBar />);
    type("шуруп");
    fireEvent.keyDown(input(), { key: "Escape" });
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("тап по опции: потеря фокуса до click не закрывает панель", async () => {
    await search();
    const option = screen.getByRole("option", { name: /Шурупы/ });
    fireEvent.pointerDown(option);
    fireEvent.blur(input());
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.click(option);
    expect(nav.push).toHaveBeenCalledWith("/catalog/krepezh?tool_type=shurupy");
  });

  it("уход фокуса Tab-ом закрывает панель", async () => {
    await search();
    fireEvent.blur(input(), { relatedTarget: document.body });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("клик вне поиска закрывает панель", async () => {
    await search();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("смена адреса закрывает панель", async () => {
    const { rerender } = render(<SearchBar />);
    fireEvent.focus(input());
    type("шуруп");
    await settle();
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    nav.pathname = "/catalog";
    rerender(<SearchBar />);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("пустой ответ — «ничего не найдено», выход на полный поиск остаётся", async () => {
    respond(EMPTY);
    await search();
    expect(screen.getByText("Ничего не найдено по запросу «шуруп»")).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Все результаты по запросу «шуруп»" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ничего не найдено", { selector: "[aria-live]" })).toBeInTheDocument();
  });

  it("ошибка — сообщение и опция «Все результаты…»", async () => {
    respond({ detail: "boom" }, false);
    await search();
    const message = screen.getByText("Не удалось загрузить подсказки", {
      selector: "p:not([aria-live])",
    });
    expect(message).toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: "Все результаты по запросу «шуруп»" }));
    expect(nav.push).toHaveBeenCalledWith(`/search?q=${encodeURIComponent("шуруп")}`);
  });

  it("пока ждём ответ — «Ищем…»", async () => {
    render(<SearchBar />);
    fireEvent.focus(input());
    type("шуруп");
    expect(screen.getByText("Ищем…")).toBeInTheDocument();
    await settle();
    expect(screen.queryByText("Ищем…")).not.toBeInTheDocument();
  });

  it("live-регион сообщает сводку ответа", async () => {
    await search();
    const live = document.querySelector("[aria-live='polite']");
    expect(live).toHaveTextContent("Найдено: 2 раздела, 1 товар");
  });
});
