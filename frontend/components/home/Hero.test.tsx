import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Hero } from "./Hero";
import { HOME_CONTENT } from "@/lib/home-content";

// #587: hero-фотобаннер — заголовок и преимущества.
describe("Hero (#587)", () => {
  it("показывает заголовок, подзаголовок и 4 преимущества", () => {
    render(<Hero />);
    expect(screen.getByRole("heading", { name: HOME_CONTENT.hero.titleLine1 })).toBeInTheDocument();
    expect(screen.getByText(HOME_CONTENT.hero.titleLine2)).toBeInTheDocument();
    for (const b of HOME_CONTENT.hero.bullets) {
      expect(screen.getByText(b.text)).toBeInTheDocument();
    }
  });

  it("кнопок на первом экране нет", () => {
    render(<Hero />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("не дублирует единый MAX-блок из подвала", () => {
    render(<Hero />);
    expect(screen.queryByText(/MAX/)).not.toBeInTheDocument();
  });
});
