import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProductTabs, type ProductTab } from "./ProductTabs";

const TABS: ProductTab[] = [
  { id: "overview", label: "О товаре", content: <p>Главное в работе</p> },
  { id: "characteristics", label: "Характеристики", content: <p>Технический паспорт</p> },
  { id: "description", label: "Описание", content: <p>Текст описания</p> },
];

// jsdom не умеет scrollIntoView — подменяем на шпион, чтобы видеть, кто крутит страницу.
const scrollIntoView = vi.fn();
const scrollTo = vi.fn();

function setHash(hash: string) {
  window.history.replaceState(null, "", hash ? `/product/perforator${hash}` : "/product/perforator");
}

function renderTabs(extraLinks?: React.ReactNode) {
  return render(<ProductTabs tabs={TABS} extraLinks={extraLinks} />);
}

function visiblePanels() {
  return screen.getAllByRole("tabpanel", { hidden: true }).filter((panel) => !panel.hidden);
}

function tab(name: string) {
  return screen.getByRole("tab", { name });
}

beforeEach(() => {
  setHash("");
  scrollIntoView.mockClear();
  scrollTo.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView;
  window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProductTabs", () => {
  it("по умолчанию открыта «О товаре», остальные панели в DOM, но скрыты", () => {
    renderTabs();
    expect(tab("О товаре")).toHaveAttribute("aria-selected", "true");
    expect(visiblePanels()).toHaveLength(1);
    expect(visiblePanels()[0]).toHaveAttribute("id", "overview");
    // Серверный контент рендерится ровно один раз — без дублей.
    expect(screen.getAllByText("Технический паспорт", { selector: "p" })).toHaveLength(1);
  });

  it("проставляет связки tab ↔ tabpanel и roving tabIndex", () => {
    renderTabs();
    const list = screen.getByRole("tablist", { name: "Разделы карточки товара" });
    expect(list).toBeInTheDocument();
    for (const t of TABS) {
      const button = document.getElementById(`tab-${t.id}`)!;
      const panel = document.getElementById(t.id)!;
      expect(button).toHaveAttribute("role", "tab");
      expect(button).toHaveAttribute("aria-controls", t.id);
      expect(panel).toHaveAttribute("role", "tabpanel");
      expect(panel).toHaveAttribute("aria-labelledby", `tab-${t.id}`);
      expect(panel).toHaveAttribute("tabindex", "0");
    }
    expect(tab("О товаре")).toHaveAttribute("tabindex", "0");
    expect(tab("Характеристики")).toHaveAttribute("tabindex", "-1");
    expect(tab("Описание")).toHaveAttribute("tabindex", "-1");
  });

  it("клик показывает только выбранную панель и не перемонтирует контент", () => {
    renderTabs();
    const passport = screen.getByText("Технический паспорт");

    fireEvent.click(tab("Характеристики"));
    expect(visiblePanels().map((p) => p.id)).toEqual(["characteristics"]);
    expect(tab("Характеристики")).toHaveAttribute("aria-selected", "true");
    expect(tab("О товаре")).toHaveAttribute("aria-selected", "false");

    fireEvent.click(tab("Описание"));
    fireEvent.click(tab("Характеристики"));
    // Тот же DOM-узел: панель только пряталась, а не создавалась заново.
    expect(screen.getByText("Технический паспорт")).toBe(passport);
  });

  it("быстрые клики в любом порядке оставляют ровно одну панель", () => {
    renderTabs();
    const order = [
      "Описание",
      "О товаре",
      "Характеристики",
      "Описание",
      "Характеристики",
      "О товаре",
      "Описание",
    ];
    for (const name of order) {
      fireEvent.click(tab(name));
      expect(visiblePanels()).toHaveLength(1);
    }
    expect(visiblePanels()[0].id).toBe("description");
    const selected = screen
      .getAllByRole("tab")
      .filter((t) => t.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(1);
  });

  it("клик меняет хэш через replaceState и не крутит страницу", () => {
    const replaceState = vi.spyOn(window.history, "replaceState");
    const stateBefore = window.history.state;
    renderTabs();

    fireEvent.click(tab("Описание"));

    expect(replaceState).toHaveBeenCalledWith(stateBefore, "", "#description");
    expect(window.location.hash).toBe("#description");
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("стрелки ходят по кругу, Home/End — к краям, фокус переезжает на вкладку", () => {
    renderTabs();
    const first = tab("О товаре");
    first.focus();

    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(tab("Характеристики")).toHaveFocus();
    expect(tab("Характеристики")).toHaveAttribute("aria-selected", "true");
    expect(tab("Характеристики")).toHaveAttribute("tabindex", "0");
    expect(first).toHaveAttribute("tabindex", "-1");

    fireEvent.keyDown(tab("Характеристики"), { key: "ArrowRight" });
    fireEvent.keyDown(tab("Описание"), { key: "ArrowRight" });
    expect(first).toHaveFocus(); // с последней — на первую

    fireEvent.keyDown(first, { key: "ArrowLeft" });
    expect(tab("Описание")).toHaveFocus(); // с первой — на последнюю

    fireEvent.keyDown(tab("Описание"), { key: "Home" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "End" });
    expect(tab("Описание")).toHaveFocus();
    expect(visiblePanels().map((p) => p.id)).toEqual(["description"]);
    expect(window.location.hash).toBe("#description");
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("прямой URL с хэшем вкладки открывает её и показывает полосу вкладок", () => {
    setHash("#characteristics");
    renderTabs();
    expect(visiblePanels().map((p) => p.id)).toEqual(["characteristics"]);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView.mock.contexts[0]).toBe(screen.getByRole("tablist"));
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start" });
  });

  it("хэш отсутствующей у товара вкладки открывает «О товаре» без прокрутки", () => {
    setHash("#description");
    render(<ProductTabs tabs={TABS.slice(0, 2)} />);
    expect(visiblePanels().map((p) => p.id)).toEqual(["overview"]);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("переход по якорю вкладки (hashchange) переключает её", () => {
    renderTabs();
    act(() => {
      setHash("#description");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
      // Браузер при переходе по якорю шлёт ещё и popstate — прокрутка одна.
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(visiblePanels().map((p) => p.id)).toEqual(["description"]);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("чужой хэш (#reviews, #compatible) вкладку не сбрасывает", () => {
    renderTabs();
    fireEvent.click(tab("Характеристики"));
    act(() => {
      setHash("#reviews");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
      setHash("#compatible");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(visiblePanels().map((p) => p.id)).toEqual(["characteristics"]);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("чужой хэш при загрузке оставляет «О товаре»", () => {
    setHash("#reviews");
    renderTabs();
    expect(visiblePanels().map((p) => p.id)).toEqual(["overview"]);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("ссылки «Совместимость»/«Отзывы» стоят вне tablist", () => {
    renderTabs(<a href="#reviews">Отзывы 3</a>);
    const link = screen.getByRole("link", { name: "Отзывы 3" });
    expect(screen.getByRole("tablist")).not.toContainElement(link);
  });
});
