import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CategoryNav } from "@/lib/listing";
import { CategoryNavStrip } from "./CategoryNav";

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

describe("CategoryNavStrip", () => {
  it("показывает все пункты сразу — строка листается свайпом, без «показать ещё»", () => {
    render(<CategoryNavStrip nav={types()} onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Тип 1\b/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Тип 12/ })).toBeInTheDocument();
  });

  it("сообщает выбранный тип родителю", () => {
    const onSelect = vi.fn();
    render(<CategoryNavStrip nav={types(3)} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /Тип 2/ }));

    expect(onSelect).toHaveBeenCalledWith("type-2", "Тип 2");
  });

  it("отмечает активный тип", () => {
    render(<CategoryNavStrip nav={types(12, "type-12")} onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Тип 12/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("подкатегорию рендерит ссылкой, а не переключателем", () => {
    render(<CategoryNavStrip nav={subcategories} onSelect={vi.fn()} />);

    expect(screen.getByRole("link", { name: "Отвёртки" })).toHaveAttribute(
      "href",
      "/catalog/ruchnoy-otvertki",
    );
  });
});
