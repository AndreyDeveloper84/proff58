import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { groupProductSpecs } from "@/lib/spec-groups";
import type { ProductDetail } from "@/lib/types";
import {
  hasPassportSpecs,
  ProductDescription,
  ProductOverview,
  ProductPassport,
  selectKeySpecs,
} from "./ProductDetailsShowcase";

// Порядок — как его отдаёт detail-эндпоинт (DATA-01): ключевые по типу товара, затем
// остальные, служебный тип инструмента — последним.
const specs = [
  { label: "Энергия удара", value: "3 Дж", slug: "energy_impact", isKey: true },
  { label: "Мощность", value: "800 Вт", slug: "power", isKey: true },
  { label: "Тип патрона", value: "SDS-plus", slug: "chuck", isKey: true },
  { label: "Питание", value: "Сеть", slug: "power_source", isKey: true },
  { label: "Вес", value: "2,7 кг", slug: "weight_kg", isKey: true },
  { label: "Режимы работы", value: "3", slug: "modes", isKey: false },
  { label: "Тип инструмента", value: "Перфораторы", slug: "tool_type", isKey: true },
];

describe("ProductDetailsShowcase", () => {
  it("«Главное в работе» берёт порядок backend, а не угадывает по подписям", () => {
    expect(selectKeySpecs(specs).map((spec) => spec.label)).toEqual([
      "Энергия удара",
      "Мощность",
      "Тип патрона",
      "Питание",
    ]);
  });

  it("неключевые характеристики и тип инструмента в «главное» не попадают", () => {
    const labels = selectKeySpecs(specs, 10).map((spec) => spec.label);
    expect(labels).not.toContain("Режимы работы");
    expect(labels).not.toContain("Тип инструмента");
  });

  it("раскладывает характеристики по разделам технического паспорта", () => {
    const groups = groupProductSpecs(specs);

    expect(groups.map((group) => group.title)).toEqual([
      "Производительность",
      "Оснастка",
      "Питание и корпус",
      "Дополнительно",
    ]);
    expect(groups[0].specs.map((spec) => spec.label)).toEqual(["Энергия удара", "Мощность"]);
    expect(groups[1].specs.map((spec) => spec.label)).toEqual(["Тип патрона", "Режимы работы"]);
    expect(groups[2].specs.map((spec) => spec.label)).toEqual(["Питание", "Вес"]);
    expect(groups[3].specs.map((spec) => spec.label)).toEqual(["Тип инструмента"]);
  });

  it("не оставляет пустые группы", () => {
    expect(groupProductSpecs([{ label: "Цвет", value: "Зелёный" }])).toHaveLength(1);
  });
});

describe("наполнение карточки", () => {
  // 12 250 товаров каталога имеют единственную «характеристику» — тип инструмента.
  // Это служебная строка разбора, а не паспорт: таблица из неё одной читалась как
  // обрезанная.
  it("считает паспорт пустым, когда есть только тип инструмента", () => {
    expect(hasPassportSpecs([{ label: "Тип инструмента", value: "Газонокосилки" }])).toBe(false);
    expect(hasPassportSpecs([])).toBe(false);
  });

  it("видит паспорт при любой настоящей характеристике", () => {
    expect(
      hasPassportSpecs([
        { label: "Тип инструмента", value: "Перфораторы" },
        { label: "Мощность", value: "950 Вт" },
      ]),
    ).toBe(true);
  });
});

describe("куски вкладок карточки", () => {
  const product = {
    specs,
    description: "Короткое описание перфоратора",
  } as unknown as ProductDetail;

  it("«О товаре» — без паспорта и описания, но с «Главным в работе» и специалистом", () => {
    render(createElement(ProductOverview, { product }));
    expect(screen.getByText("Главное в работе")).toBeInTheDocument();
    expect(screen.queryByText("Технический паспорт")).not.toBeInTheDocument();
    expect(screen.queryByText("Короткое описание перфоратора")).not.toBeInTheDocument();
    expect(document.querySelector('[data-event="pdp_expert_help"]')).not.toBeNull();
  });

  it("«О товаре» без паспорта всё равно не пустая: остаётся панель специалиста", () => {
    const bare = { specs: [], description: "" } as unknown as ProductDetail;
    render(createElement(ProductOverview, { product: bare }));
    expect(screen.queryByText("Главное в работе")).not.toBeInTheDocument();
    expect(screen.getByText("Задать вопрос специалисту")).toBeInTheDocument();
  });

  // Якоря #characteristics/#description теперь у панелей вкладок: второй такой id
  // внутри панели ломал бы и aria-controls, и переход по прямому URL.
  it("паспорт и описание не несут своих якорных id", () => {
    const { container } = render(
      createElement("div", null, [
        createElement(ProductPassport, { key: "p", specs }),
        createElement(ProductDescription, { key: "d", description: "Текст" }),
      ]),
    );
    expect(screen.getByText("Технический паспорт")).toBeInTheDocument();
    expect(container.querySelector("#characteristics, #description")).toBeNull();
  });

  it("длинный паспорт сворачивается и растворяется в фоне панели, а не в белом", () => {
    const many = Array.from({ length: 15 }, (_, i) => ({ label: `Параметр ${i}`, value: `${i}` }));
    render(createElement(ProductPassport, { specs: many }));
    const toggle = screen.getByRole("button", { name: /Все характеристики/ });
    const region = document.getElementById(toggle.getAttribute("aria-controls")!);
    expect(region).not.toBeNull();
    expect(region!.querySelector(".from-raised")).not.toBeNull();
    expect(region!.querySelector(".from-surface")).toBeNull();
  });

  it("длинное описание сворачивается в цвет своей карточки", () => {
    render(createElement(ProductDescription, { description: "а".repeat(700) }));
    const toggle = screen.getByRole("button", { name: /Показать всё/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const region = document.getElementById(toggle.getAttribute("aria-controls")!);
    expect(region!.querySelector(".from-surface")).not.toBeNull();
  });
});
