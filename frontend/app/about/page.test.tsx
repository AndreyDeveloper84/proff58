import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AboutPage, { metadata } from "./page";

// Главное требование тикета к этой странице — не выдумывать (DRF-1009).
// Тест сторожит именно это: цифры доверия, сроки и обещания появляются на
// странице только вместе с подтверждением от владельца.
describe("Страница «О компании»", () => {
  it("рассказывает о магазине по разделам", () => {
    render(<AboutPage />);

    expect(screen.getByRole("heading", { level: 1, name: "О компании" })).toBeInTheDocument();
    const sections = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(sections).toEqual([
      "Магазин и ассортимент",
      "Помогаем выбрать, а не просто продаём",
      "Организациям",
      "Сервис и поддержка после покупки",
      "Как нас найти",
    ]);
  });

  it("у каждой фотографии есть осмысленный alt", () => {
    render(<AboutPage />);

    const images = screen.getAllByRole("img");
    expect(images.length).toBeGreaterThanOrEqual(5);
    for (const img of images) {
      expect(img.getAttribute("alt")?.length ?? 0).toBeGreaterThan(10);
    }
  });

  it("даёт позвонить и построить маршрут", () => {
    render(<AboutPage />);

    expect(screen.getAllByRole("link", { name: /8 \(800\)/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Построить маршрут" })).toHaveAttribute(
      "href",
      expect.stringContaining("yandex.ru/maps"),
    );
    expect(screen.getByRole("link", { name: "Перейти в каталог" })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  // Владелец не подтверждал ни лет работы, ни числа клиентов и товаров.
  // Такие цифры на странице о доверии работают против доверия.
  it("не содержит неподтверждённых цифр доверия", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/\d+\s*(лет|года)\s+(на рынке|работаем|опыта)/i);
    expect(text).not.toMatch(/\d[\d\s]*\s*(клиент|довольных|товаров в наличии)/i);
    expect(text).not.toMatch(/лучш(ие|ая) цен|дешевле всех|гарантия \d+ (лет|год)/i);
  });

  // Сроки ремонта и условия гарантии магазин не подтверждал — до страницы
  // «Гарантийный ремонт» здесь только приглашение позвонить.
  it("не обещает сроков ремонта", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/ремонт за \d+|в течение \d+ дн|срок ремонта \d+/i);
  });

  it("метаданные заполнены и canonical ведёт на себя", () => {
    expect(metadata.title).toMatch(/О компании/);
    expect(String(metadata.description ?? "")).toMatch(/Пенз/);
    expect(metadata.alternates?.canonical).toBe("/about");
  });
});
