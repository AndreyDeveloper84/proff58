import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryHero } from "./CategoryHero";

// Task 5: один <h1>, вариант inline рендерится, счётчик склоняется, intro опционально.
describe("CategoryHero", () => {
  it("рендерит единственный <h1> с названием", () => {
    render(<CategoryHero title="Шуруповёрты" />);
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent("Шуруповёрты");
  });

  it("склоняет счётчик и группирует разряды", () => {
    const { rerender } = render(<CategoryHero title="К" total={1} />);
    expect(screen.getByText("1 товар")).toBeInTheDocument();
    rerender(<CategoryHero title="К" total={2} />);
    expect(screen.getByText("2 товара")).toBeInTheDocument();
    rerender(<CategoryHero title="К" total={5} />);
    expect(screen.getByText("5 товаров")).toBeInTheDocument();
    // Разряды группируются (ru-locale, пробел-разделитель может быть NBSP → regex).
    rerender(<CategoryHero title="К" total={1248} />);
    expect(screen.getByText(/1.248.товаров/)).toBeInTheDocument();
  });

  it("вариант inline рендерится и показывает заголовок", () => {
    render(<CategoryHero title="Дрели" variant="inline" total={5} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Дрели");
    expect(screen.getByText("5 товаров")).toBeInTheDocument();
  });

  it("intro опционально: без него нет описания", () => {
    const { rerender } = render(<CategoryHero title="К" />);
    expect(screen.queryByText(/Описание/)).toBeNull();
    rerender(<CategoryHero title="К" intro="Описание категории" />);
    expect(screen.getByText("Описание категории")).toBeInTheDocument();
  });
});
