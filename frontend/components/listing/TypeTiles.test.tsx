import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TypeTiles } from "./TypeTiles";
import type { CategoryNavItem } from "@/lib/listing";

// Числа — реальный состав «Электроинструмента» со стенда (DRF-991 §7).
const ELECTRO: [string, string, number][] = [
  ["dreli", "Дрели и шуруповёрты", 337],
  ["shlifmashiny", "Шлифовальные машины", 247],
  ["pily", "Пилы", 150],
  ["perforatory", "Перфораторы", 125],
  ["bolgarki", "Болгарки (УШМ)", 57],
  ["gaikoverty", "Гайковёрты", 47],
  ["lobziki", "Лобзики", 45],
  ["feny", "Фены строительные", 31],
  ["pylesosy", "Строительные пылесосы", 30],
  ["tochila", "Точила и наждаки", 28],
  ["otboyniki", "Отбойные молотки", 28],
  ["rubanki", "Электрорубанки", 27],
  ["zaryadnye", "Зарядные устройства", 25],
  ["frezery", "Фрезеры", 21],
];

function items(source = ELECTRO): CategoryNavItem[] {
  return source.map(([key, label, count]) => ({ key, label, count, active: false }));
}

describe("TypeTiles", () => {
  it("заголовок берёт родительный падеж раздела", () => {
    render(<TypeTiles categoryTitle="Электроинструмент" items={items()} onSelect={() => {}} />);

    expect(screen.getByText("Популярные виды электроинструмента")).toBeInTheDocument();
  });

  // Стена из 44 капсул — то, ради чего блок и переписан: показываем ровно 12.
  it("показывает 12 плиток, остальные прячет под кнопку", () => {
    render(<TypeTiles categoryTitle="Электроинструмент" items={items()} onSelect={() => {}} />);

    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(12);
    expect(screen.getByText("Показать все виды электроинструмента")).toBeInTheDocument();
    expect(screen.queryByText("Зарядные устройства")).not.toBeInTheDocument();
  });

  it("кнопка раскрывает полный список и сворачивает обратно", () => {
    render(<TypeTiles categoryTitle="Электроинструмент" items={items()} onSelect={() => {}} />);

    fireEvent.click(screen.getByText("Показать все виды электроинструмента"));
    expect(screen.getByText("Зарядные устройства")).toBeInTheDocument();
    expect(screen.getByText("Фрезеры")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Свернуть"));
    expect(screen.queryByText("Зарядные устройства")).not.toBeInTheDocument();
  });

  it("кнопки нет, когда скрывать нечего", () => {
    render(
      <TypeTiles categoryTitle="Электроинструмент" items={items(ELECTRO.slice(0, 4))} onSelect={() => {}} />,
    );

    expect(screen.queryByText(/Показать все виды/)).not.toBeInTheDocument();
  });

  it("плитка показывает количество товаров и передаёт выбор наружу", () => {
    const onSelect = vi.fn();
    render(<TypeTiles categoryTitle="Электроинструмент" items={items()} onSelect={onSelect} />);

    expect(screen.getByText("337")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Дрели и шуруповёрты"));

    expect(onSelect).toHaveBeenCalledWith("dreli", "Дрели и шуруповёрты");
  });

  it("активный тип отмечен для скринридера", () => {
    const withActive = items().map((i) => (i.key === "pily" ? { ...i, active: true } : i));
    render(<TypeTiles categoryTitle="Электроинструмент" items={withActive} onSelect={() => {}} />);

    expect(screen.getAllByRole("button", { pressed: true })).toHaveLength(1);
  });

  // Дерево каталога растёт на бэкенде: незнакомый раздел не должен ломать подписи.
  it("незнакомый раздел — подписи без падежа, а не «виды undefined»", () => {
    render(<TypeTiles categoryTitle="Батискафы" items={items()} onSelect={() => {}} />);

    expect(screen.getByText("Популярные виды")).toBeInTheDocument();
    expect(screen.getByText("Показать все виды")).toBeInTheDocument();
  });
});
