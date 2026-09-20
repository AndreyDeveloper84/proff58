import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProductSpecs } from "./ProductSpecs";

// DATA-01: раньше карточка показывала «Да · 505 мм · 76 шт.» — числа без названий.
describe("ProductSpecs (DATA-01)", () => {
  const specs = [
    { label: "Длина шины", value: "505 мм", slug: "bar_length" },
    { label: "Количество звеньев", value: "76 шт.", slug: "chain_links" },
    { label: "Мощность", value: "2,2 кВт", slug: "power" },
    { label: "Масса", value: "6 кг", slug: "weight_kg" },
    { label: "Тип инструмента", value: "Бензопилы", slug: "tool_type" },
  ];

  it("каждое значение подписано, безымянной строки через «·» нет", () => {
    const { container } = render(<ProductSpecs specs={specs} />);

    expect(screen.getByText("Длина шины:")).toBeInTheDocument();
    expect(screen.getByText("505 мм")).toBeInTheDocument();
    expect(container.textContent).not.toContain("·");
    // Семантика: пары термин–значение, а не абзац.
    expect(container.querySelectorAll("dt")).toHaveLength(3);
    expect(container.querySelectorAll("dd")).toHaveLength(3);
  });

  it("показывает не больше лимита и не показывает тип инструмента", () => {
    render(<ProductSpecs specs={specs} limit={2} />);

    expect(screen.queryByText("Мощность:")).not.toBeInTheDocument();
    expect(screen.queryByText("Тип инструмента:")).not.toBeInTheDocument();
  });

  it("длинное значение обрезается, но доступно целиком в подсказке", () => {
    const long = "для перфораторов с патроном SDS-plus и SDS-max, бетон и кирпич";
    render(<ProductSpecs specs={[{ label: "Назначение", value: long, slug: "purpose" }]} />);

    expect(screen.getByText(long)).toHaveAttribute("title", long);
  });

  it("без характеристик ничего не рисует — ни пустых строк, ни заглушек", () => {
    const { container } = render(
      <ProductSpecs specs={[{ label: "Тип инструмента", value: "Газонокосилки", slug: "tool_type" }]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
