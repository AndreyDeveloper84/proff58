import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Facet } from "@/lib/types";
import { TypePanel } from "./TypePanel";

function facet(count = 15): Facet {
  return {
    code: "tool_type",
    label: "Тип инструмента",
    type: "checkbox",
    isNav: true,
    options: Array.from({ length: count }, (_, index) => ({
      value: `type-${index + 1}`,
      label: `Тип ${index + 1}`,
      count: index + 1,
      selected: false,
    })),
  };
}

describe("TypePanel", () => {
  it("сворачивает длинный список типов и раскрывает его по кнопке", () => {
    render(<TypePanel facet={facet()} onSelect={vi.fn()} />);

    expect(screen.getByText("Тип 12")).toBeInTheDocument();
    expect(screen.queryByText("Тип 13")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Показать ещё (3)" }));

    expect(screen.getByText("Тип 13")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Свернуть типы" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("оставляет активный тип видимым в свёрнутом состоянии", () => {
    render(
      <TypePanel
        facet={facet()}
        active="type-15"
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /Тип 15/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
