import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Hero } from "./Hero";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";

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

  it("плашка MAX ведёт на внешний канал в новой вкладке", () => {
    render(<Hero onConsult={() => {}} />);
    const max = screen.getByRole("link", { name: /Консультация в MAX/ });
    expect(max).toHaveAttribute("href", SITE.support.max.href);
    expect(max).toHaveAttribute("target", "_blank");
    expect(max).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});
