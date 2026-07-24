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
});

