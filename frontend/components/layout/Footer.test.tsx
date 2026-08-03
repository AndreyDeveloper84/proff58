import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Footer } from "./Footer";
import { resolveStorefront, SITE } from "@/lib/site";

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

// Адрес бота приходит с сервера (max_bot_url в /api/core/theme/), поэтому в
// тестах подставляем его как настроенный магазин.
const BOT_URL = "https://max.ru/proff58_bot";
const withBot = { ...resolveStorefront(), maxHref: BOT_URL };

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

  it("плитка ведёт в бота магазина и описывает то, что он умеет", () => {
    render(<Footer storefront={withBot} />);
    const max = screen.getByRole("link", { name: new RegExp(SITE.maxBot.title) });
    expect(max).toHaveAttribute("href", BOT_URL);
    expect(max).toHaveAttribute("target", "_blank");
    expect(screen.getByText(SITE.maxBot.text)).toBeInTheDocument();
  });

  // Раньше ссылка была захардкожена как https://max.ru/ — плитка выглядела
  // рабочей, но вела на главную мессенджера, а не к магазину.
  it("без настроенного бота плитки нет вовсе", () => {
    const { container } = render(<Footer />);
    expect(container.querySelector('a[data-event="footer_max"]')).toBeNull();
  });

  it("в плитке показан фирменный логотип MAX", () => {
    const { container } = render(<Footer storefront={withBot} />);
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
});
