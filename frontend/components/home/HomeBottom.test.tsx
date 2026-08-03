import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeBottom } from "./HomeBottom";
import { ARTICLES } from "@/lib/articles";
import { HOME_CONTENT } from "@/lib/home-content";

// #590: нижняя зона — почему покупают, лента статей, подписка-заглушка.
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

  // Подписка убрана: backend рассылок нет, неактивные поле и кнопка читались как
  // поломка сайта. Проверяем именно отсутствие — чтобы заглушка не вернулась молча.
  it("не показывает форму подписки", () => {
    render(<HomeBottom />);
    expect(screen.queryByLabelText("E-mail для подписки")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Подписаться/ })).not.toBeInTheDocument();
  });

  // Карточка MAX-помощи убрана: она дублировала подвал, который идёт сразу под
  // ней, и hero-кнопку той же страницы. В нижней зоне ссылок на MAX быть не должно.
  it("не зовёт в MAX: канал остался в hero и подвале", () => {
    render(<HomeBottom />);
    expect(screen.queryByText(/MAX/)).not.toBeInTheDocument();
    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toContain("max.ru");
    }
  });
});
