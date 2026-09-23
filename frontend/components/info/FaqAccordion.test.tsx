import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FaqAccordion } from "./FaqAccordion";

const ITEMS = [
  { title: "Первый вопрос", text: "Первый ответ" },
  { title: "Средний вопрос", text: "Средний ответ" },
  { title: "Последний вопрос", text: "Последний ответ" },
];

function openAnswers() {
  return ITEMS.filter((item) => screen.getByText(item.text).closest("[hidden]") === null).map(
    (item) => item.title,
  );
}

describe("FaqAccordion", () => {
  it("по умолчанию открыт первый вопрос, кнопки связаны с ответами", () => {
    render(<FaqAccordion items={ITEMS} />);

    expect(openAnswers()).toEqual(["Первый вопрос"]);
    const first = screen.getByRole("button", { name: /Первый вопрос/ });
    expect(first).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(first.getAttribute("aria-controls")!);
    expect(panel).toHaveTextContent("Первый ответ");
    expect(screen.getByRole("button", { name: /Средний вопрос/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("первая → последняя → средняя: всегда открыт ровно один", () => {
    render(<FaqAccordion items={ITEMS} />);

    fireEvent.click(screen.getByRole("button", { name: /Последний вопрос/ }));
    expect(openAnswers()).toEqual(["Последний вопрос"]);
    fireEvent.click(screen.getByRole("button", { name: /Средний вопрос/ }));
    expect(openAnswers()).toEqual(["Средний вопрос"]);
  });

  it("повторный и быстрый клик по открытому вопросу его не закрывает", () => {
    render(<FaqAccordion items={ITEMS} />);
    const middle = screen.getByRole("button", { name: /Средний вопрос/ });

    for (let i = 0; i < 5; i += 1) fireEvent.click(middle);
    expect(openAnswers()).toEqual(["Средний вопрос"]);
    expect(middle).toHaveAttribute("aria-expanded", "true");
  });

  it("стрелки и Home/End переводят фокус между вопросами", () => {
    render(<FaqAccordion items={ITEMS} />);
    const [first, middle, last] = screen.getAllByRole("button");

    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(middle).toHaveFocus();
    fireEvent.keyDown(middle, { key: "End" });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: "ArrowDown" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "ArrowUp" });
    expect(last).toHaveFocus();
  });

  it("две группы на странице не влияют друг на друга", () => {
    render(
      <>
        <FaqAccordion items={ITEMS} />
        <FaqAccordion
          items={[
            { title: "Другой А", text: "Ответ А" },
            { title: "Другой Б", text: "Ответ Б" },
          ]}
        />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Последний вопрос/ }));
    expect(screen.getByText("Ответ А").closest("[hidden]")).toBeNull();
    expect(screen.getByRole("button", { name: /Другой А/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
