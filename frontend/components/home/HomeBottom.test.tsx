import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HOME_ARTICLES_LIMIT, HomeBottom } from "./HomeBottom";
import { ARTICLES } from "@/lib/articles";
import { HOME_CONTENT } from "@/lib/home-content";

// #590: нижняя зона — почему покупают и лента советов (раздел /articles).
const shown = ARTICLES.slice(0, HOME_ARTICLES_LIMIT);
describe("HomeBottom (#590)", () => {
  it("показывает 6 причин «почему покупают у нас»", () => {
    render(<HomeBottom />);
    for (const item of HOME_CONTENT.whyBuy) {
      expect(screen.getByText(item.title)).toBeInTheDocument();
    }
  });

  it("карточки советов ведут в раздел /articles, ссылка «Все советы» — на весь раздел", () => {
    render(<HomeBottom />);
    for (const article of shown) {
      const card = screen.getByText(article.title);
      expect(card.closest("a")).toHaveAttribute("href", `/articles/${article.slug}`);
    }
    expect(screen.getByRole("link", { name: /Все советы/ })).toHaveAttribute("href", "/articles");
    expect(screen.queryByRole("link", { name: /Все статьи/ })).toBeNull();
  });

  it("главная не перегружена: не больше трёх материалов", () => {
    render(<HomeBottom />);
    expect(HOME_ARTICLES_LIMIT).toBe(3);
    expect(ARTICLES.length).toBeGreaterThan(HOME_ARTICLES_LIMIT); // иначе проверка ниже пустая
    for (const article of ARTICLES.slice(HOME_ARTICLES_LIMIT)) {
      expect(screen.queryByText(article.title)).toBeNull();
    }
  });

  it("заголовок — советы, а не «статьи и обзоры»: полный на планшете и шире, короткий на телефоне", () => {
    render(<HomeBottom />);
    const heading = screen.getByRole("heading", { level: 2, name: /Советы по выбору/ });
    expect(screen.getByText("Советы по выбору и работе с инструментом")).toHaveClass("hidden", "sm:inline");
    expect(screen.getByText("Полезные советы")).toHaveClass("sm:hidden");
    expect(heading.closest("section")).toHaveAttribute("aria-labelledby", heading.id);
    expect(screen.queryByText(/Полезные статьи/)).toBeNull();
  });

  // Листание ленты — это стрелки на планшете/десктопе и точки на мобильной; и то
  // и другое должно быть доступно с клавиатуры и озвучено скринридеру. На xl три
  // материала видны целиком — стрелки там прячутся.
  it("у ленты советов есть управление: стрелки (кроме xl) и точки по числу материалов", () => {
    render(<HomeBottom />);
    expect(screen.getByRole("button", { name: "Предыдущие советы" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Следующие советы" })).toBeInTheDocument();
    expect(screen.getByTestId("articles-arrows")).toHaveClass("sm:flex", "xl:hidden");
    const dots = screen.getAllByRole("button", { name: /^Совет \d+:/ });
    expect(dots).toHaveLength(shown.length);
  });

  // Карточка подписки убрана вместе с планами на рассылку: неактивная форма
  // выглядела рабочей и молча ничего не делала.
  it("не показывает форму подписки", () => {
    render(<HomeBottom />);
    expect(screen.queryByLabelText("E-mail для подписки")).toBeNull();
    expect(screen.queryByText(/Подпишитесь/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Подписаться/ })).toBeNull();
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
