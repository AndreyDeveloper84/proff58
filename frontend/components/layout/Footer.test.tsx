import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Footer } from "./Footer";
import { SITE } from "@/lib/site";

// #591: светлый подвал — только рабочие маршруты, контакты из SITE, MAX-карточка.
const EXISTING_PREFIXES = [
  "/catalog",
  "/search",
  "/cart",
  "/account",
  "/articles",
  "/",
  "tel:",
  "mailto:",
  "http",
];

describe("Footer (#591)", () => {
  it("все ссылки ведут на существующие маршруты или внешние адреса", () => {
    render(<Footer />);
    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href") ?? "";
      expect(href).not.toBe("#");
      expect(
        EXISTING_PREFIXES.some((p) => href === p || href.startsWith(p)),
        `битая ссылка: ${href}`,
      ).toBe(true);
    }
  });

  it("контакты совпадают с SITE", () => {
    render(<Footer />);
    expect(screen.getByText(SITE.phone.display)).toBeInTheDocument();
    expect(screen.getByText(SITE.email)).toBeInTheDocument();
    expect(screen.getByText(SITE.address)).toBeInTheDocument();
    expect(screen.getByText(SITE.schedule)).toBeInTheDocument();
  });

  it("карточка «Мы в мессенджерах» ведёт в MAX", () => {
    render(<Footer />);
    const max = screen.getByRole("link", { name: /Мы в мессенджерах/ });
    expect(max).toHaveAttribute("href", SITE.support.max.href);
    expect(max).toHaveAttribute("target", "_blank");
  });

  it("в карточке мессенджеров показан фирменный логотип MAX", () => {
    const { container } = render(<Footer />);
    expect(container.querySelector('a[data-event="footer_max"] img')).toHaveAttribute(
      "src",
      expect.stringContaining("max-colored.png"),
    );
    expect(screen.queryByRole("img", { name: /QR-код/ })).not.toBeInTheDocument();
  });

  it("группы ссылок из конфига отрисованы", () => {
    render(<Footer />);
    for (const col of SITE.footerColumns) {
      expect(screen.getByRole("navigation", { name: col.title })).toBeInTheDocument();
    }
  });

  // Раньше в колонке «Каталог товаров» лежали шесть подписей, и все шесть вели на
  // общий /catalog — меню, которое никуда не ведёт. Теперь разделы приходят из
  // дерева категорий, и каждая ссылка открывает свой раздел.
  it("разделы каталога ведут каждый в свой раздел", () => {
    render(
      <Footer
        categories={[
          { label: "Оснастка и расходные материалы", href: "/catalog/osnastka" },
          { label: "Ручной инструмент", href: "/catalog/ruchnoy" },
        ]}
      />,
    );
    const nav = screen.getByRole("navigation", { name: "Каталог товаров" });
    expect(within(nav).getByRole("link", { name: "Ручной инструмент" })).toHaveAttribute(
      "href",
      "/catalog/ruchnoy",
    );
    expect(within(nav).getByRole("link", { name: "Все категории" })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  it("без дерева категорий колонка остаётся с одной ссылкой «Все категории»", () => {
    render(<Footer />);
    const nav = screen.getByRole("navigation", { name: "Каталог товаров" });
    expect(within(nav).getAllByRole("link")).toHaveLength(1);
    expect(within(nav).getByRole("link", { name: "Все категории" })).toBeInTheDocument();
  });
});
