import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeBottom } from "./HomeBottom";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";

// #590: нижняя зона — почему покупают, статьи-заглушки, подписка-заглушка, MAX.
describe("HomeBottom (#590)", () => {
  it("показывает 6 причин «почему покупают у нас»", () => {
    render(<HomeBottom />);
    for (const item of HOME_CONTENT.whyBuy) {
      expect(screen.getByText(item.title)).toBeInTheDocument();
    }
  });

  it("статьи — заглушки без ссылок (раздела статей нет, битых href не рисуем)", () => {
    render(<HomeBottom />);
    for (const item of HOME_CONTENT.articles.items) {
      const card = screen.getByText(item.title);
      expect(card).toBeInTheDocument();
      expect(card.closest("a")).toBeNull();
    }
    expect(screen.queryByText(/Читать все статьи/)).toBeNull();
  });

  it("подписка — UI-заглушка: поле и кнопка неактивны, причина видна", () => {
    render(<HomeBottom />);
    expect(screen.getByLabelText("E-mail для подписки")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: new RegExp(HOME_CONTENT.subscribe.cta) }),
    ).toBeDisabled();
    expect(screen.getByText(HOME_CONTENT.subscribe.note)).toBeInTheDocument();
  });

  it("MAX-карточка ведёт на внешний канал в новой вкладке", () => {
    render(<HomeBottom />);
    const link = screen.getByRole("link", { name: new RegExp(HOME_CONTENT.maxHelp.cta) });
    expect(link).toHaveAttribute("href", SITE.support.max.href);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});
