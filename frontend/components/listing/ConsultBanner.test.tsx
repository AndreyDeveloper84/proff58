import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConsultBanner } from "./ConsultBanner";
import { SITE } from "@/lib/site";

// Task 5: одна CTA-ссылка с текстом из SITE, отдельного квадрата «MAX» нет,
// аналитика consult_max_click сохранена, ссылка открывается в новой вкладке.
describe("ConsultBanner", () => {
  it("рендерит одну ссылку-CTA с текстом из SITE и сохраняет аналитику", () => {
    render(<ConsultBanner />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    const cta = links[0];
    expect(cta).toHaveTextContent(SITE.support.max.ctaLabel);
    expect(cta).toHaveAttribute("data-event", "consult_max_click");
    expect(cta).toHaveAttribute("target", "_blank");
    expect(cta).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("не содержит отдельного элемента-квадрата «MAX»", () => {
    render(<ConsultBanner />);
    expect(screen.queryByText("MAX")).toBeNull();
  });
});
