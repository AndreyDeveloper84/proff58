import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeIntentGrid } from "./HomeIntentGrid";
import { HOME_CONTENT } from "@/lib/home-content";

// #588: сценарные карточки и сервисная полоса — все ссылки валидны, без мёртвых href.
describe("HomeIntentGrid (#588)", () => {
  it("показывает 5 сценарных карточек с рабочими ссылками", () => {
    render(<HomeIntentGrid />);
    expect(
      screen.getByRole("heading", { name: HOME_CONTENT.intent.title }),
    ).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(HOME_CONTENT.intent.cards.length);
    const hrefs = links.map((link) => link.getAttribute("href"));
    for (const href of hrefs) {
      expect(href).toBeTruthy();
      expect(href).not.toBe("#");
      expect(href).toMatch(/^\/catalog\//);
    }
    // Сценарии ведут в разные разделы каталога, а не все в один /catalog.
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(screen.getByText("Для дома")).toBeInTheDocument();
    expect(screen.getByText("Расходные материалы и оснастка")).toBeInTheDocument();
  });

  // Смысл блока — узнать инструмент с одного взгляда; перекрашенная пиктограмма
  // «шестерёнка» этого не даёт, поэтому у каждой карточки своё предметное фото.
  it("у каждой карточки своё предметное фото", () => {
    const { container } = render(<HomeIntentGrid />);
    const srcs = Array.from(container.querySelectorAll("img")).map((img) =>
      decodeURIComponent(img.getAttribute("src") ?? ""),
    );

    expect(srcs).toHaveLength(HOME_CONTENT.intent.cards.length);
    for (const card of HOME_CONTENT.intent.cards) {
      expect(srcs.some((src) => src.includes(card.image))).toBe(true);
    }
  });
});

