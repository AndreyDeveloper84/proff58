import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConsultBanner } from "./ConsultBanner";
import { SITE } from "@/lib/site";

// PLP-04: компактная карточка = одна доступная ссылка (иконка→текст→квадрат MAX),
// без отдельной CTA-кнопки; аналитика consult_max_click сохранена.
describe("ConsultBanner", () => {
  it("вся карточка — одна ссылка на MAX с аналитикой", () => {
    render(<ConsultBanner />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    const card = links[0];
    expect(card).toHaveAttribute("href", SITE.support.max.href);
    expect(card).toHaveAttribute("data-event", "consult_max_click");
    expect(card).toHaveAttribute("target", "_blank");
    expect(card).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("показывает заголовок и квадрат MAX", () => {
    render(<ConsultBanner />);
    expect(screen.getByText(SITE.support.max.title)).toBeInTheDocument();
    expect(screen.getByText("MAX")).toBeInTheDocument();
  });
});
