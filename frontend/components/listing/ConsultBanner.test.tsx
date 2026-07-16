import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConsultBanner } from "./ConsultBanner";
import { SITE } from "@/lib/site";

// PLP-04: карточка не кликабельна целиком; единственная ссылка — квадрат MAX.
describe("ConsultBanner", () => {
  it("только квадрат MAX является ссылкой с аналитикой", () => {
    render(<ConsultBanner />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    const maxLink = screen.getByRole("link", { name: "Открыть MAX" });
    expect(maxLink).toHaveAttribute("href", SITE.support.max.href);
    expect(maxLink).toHaveAttribute("data-event", "consult_max_click");
    expect(maxLink).toHaveAttribute("target", "_blank");
    expect(maxLink).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("показывает заголовок и логотип MAX", () => {
    const { container } = render(<ConsultBanner />);
    expect(screen.getByText(SITE.support.max.title)).toBeInTheDocument();
    expect(container.querySelector('a[aria-label="Открыть MAX"] img')).toHaveAttribute(
      "src",
      expect.stringContaining("max-colored.png"),
    );
  });
});
