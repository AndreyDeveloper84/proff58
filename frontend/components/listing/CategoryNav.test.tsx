import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CategoryNav } from "@/lib/listing";
import { CategoryNavPanel, CategoryNavStrip } from "./CategoryNav";

function types(count = 12, activeKey?: string): CategoryNav {
  return {
    title: "Тип инструмента",
    isNavigation: false,
    items: Array.from({ length: count }, (_, index) => ({
      key: `type-${index + 1}`,
      label: `Тип ${index + 1}`,
      count: index + 1,
      active: `type-${index + 1}` === activeKey,
    })),
  };
}

const subcategories: CategoryNav = {
  title: "Разделы",
  isNavigation: true,
  items: [
    { key: "/catalog/ruchnoy-otvertki", label: "Отвёртки", href: "/catalog/ruchnoy-otvertki", active: false },
  ],
};

describe("CategoryNavPanel", () => {
  it("сворачивает длинный список и раскрывает его по кнопке", () => {
    render(<CategoryNavPanel nav={types()} onSelect={vi.fn()} />);

    expect(screen.getByText("Тип 8")).toBeInTheDocument();
    expect(screen.queryByText("Тип 9")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Показать ещё (4)" }));

    expect(screen.getByText("Тип 9")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Свернуть" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("оставляет активный тип видимым в свёрнутом состоянии", () => {
    render(<CategoryNavPanel nav={types(12, "type-12")} onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Тип 12/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("сообщает выбранный тип родителю", () => {
    const onSelect = vi.fn();
    render(<CategoryNavPanel nav={types(3)} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /Тип 2/ }));

    expect(onSelect).toHaveBeenCalledWith("type-2", "Тип 2");
  });

  it("подкатегорию рендерит ссылкой, а не переключателем", () => {
    render(<CategoryNavPanel nav={subcategories} onSelect={vi.fn()} />);

    expect(screen.getByRole("link", { name: "Отвёртки" })).toHaveAttribute(
      "href",
      "/catalog/ruchnoy-otvertki",
    );
  });
});

describe("CategoryNavStrip", () => {
  it("показывает на мобильном все пункты сразу — список листается свайпом", () => {
    render(<CategoryNavStrip nav={types()} onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Тип 12/ })).toBeInTheDocument();
  });
});
