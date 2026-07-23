import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeIntentGrid } from "./HomeIntentGrid";
import { HomeServiceStrip } from "./HomeServiceStrip";
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
    for (const link of links) {
      const href = link.getAttribute("href");
      expect(href).toBeTruthy();
      expect(href).not.toBe("#");
    }
    expect(screen.getByText("Для дома")).toBeInTheDocument();
    expect(screen.getByText("Расходные материалы и оснастка")).toBeInTheDocument();
  });
});

describe("HomeServiceStrip (#588)", () => {
  it("показывает 5 пунктов сервисной полосы", () => {
    render(<HomeServiceStrip />);
    for (const item of HOME_CONTENT.serviceStrip) {
      expect(screen.getByText(item.title)).toBeInTheDocument();
    }
  });
});
