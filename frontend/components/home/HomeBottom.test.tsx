import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeBottom } from "./HomeBottom";
import { ARTICLES } from "@/lib/articles";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";

// #590: нижняя зона — почему покупают, лента статей, подписка-заглушка, MAX.
describe("HomeBottom (#590)", () => {
  it("показывает 6 причин «почему покупают у нас»", () => {
    render(<HomeBottom />);
    for (const item of HOME_CONTENT.whyBuy) {
      expect(screen.getByText(item.title)).toBeInTheDocument();
    }
  });

  it("карточки статей ведут в раздел /articles", () => {
    render(<HomeBottom />);
    for (const article of ARTICLES) {
      const card = screen.getByText(article.title);
      expect(card.closest("a")).toHaveAttribute("href", `/articles/${article.slug}`);
    }
    expect(screen.getByRole("link", { name: /Все статьи/ })).toHaveAttribute("href", "/articles");
  });

  // Листание ленты — это стрелки на десктопе и точки на мобильной; и то и другое
  // должно быть доступно с клавиатуры и озвучено скринридеру.
  it("у ленты статей есть управление: стрелки и точки по числу статей", () => {
    render(<HomeBottom />);
    expect(screen.getByRole("button", { name: "Предыдущие статьи" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Следующие статьи" })).toBeInTheDocument();
    const dots = screen.getAllByRole("button", { name: /^Статья \d+:/ });
    expect(dots).toHaveLength(ARTICLES.length);
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
