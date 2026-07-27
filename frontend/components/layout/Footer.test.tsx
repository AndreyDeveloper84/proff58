import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Footer } from "./Footer";
import { SITE } from "@/lib/site";

// #591: светлый подвал — только рабочие маршруты, контакты из SITE, MAX-карточка.
const EXISTING_PREFIXES = ["/catalog", "/search", "/cart", "/account", "/", "tel:", "mailto:", "http"];

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

  it("группы ссылок из конфига отрисованы", () => {
    render(<Footer />);
    for (const col of SITE.footerColumns) {
      expect(screen.getByRole("navigation", { name: col.title })).toBeInTheDocument();
    }
  });
});
