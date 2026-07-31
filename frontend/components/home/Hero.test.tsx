import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Hero } from "./Hero";
import { HOME_CONTENT } from "@/lib/home-content";

// #587: hero-фотобаннер — заголовок, преимущества и рабочие CTA.
describe("Hero (#587)", () => {
  it("показывает заголовок, подзаголовок и 4 преимущества", () => {
    render(<Hero onConsult={() => {}} />);
    expect(screen.getByRole("heading", { name: HOME_CONTENT.hero.titleLine1 })).toBeInTheDocument();
    expect(screen.getByText(HOME_CONTENT.hero.titleLine2)).toBeInTheDocument();
    for (const b of HOME_CONTENT.hero.bullets) {
      expect(screen.getByText(b.text)).toBeInTheDocument();
    }
  });

  it("«Подобрать инструмент» открывает подбор, «Перейти в каталог» ведёт в /catalog", () => {
    const onConsult = vi.fn();
    render(<Hero onConsult={onConsult} />);
    fireEvent.click(screen.getByRole("button", { name: /Подобрать инструмент/ }));
    expect(onConsult).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: /Перейти в каталог/ })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  it("не дублирует единый MAX-блок из подвала", () => {
    render(<Hero onConsult={() => {}} />);
    expect(screen.queryByText(/MAX/)).not.toBeInTheDocument();
  });
});
