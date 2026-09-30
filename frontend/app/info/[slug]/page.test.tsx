import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// DRF-2495: контакты страниц из кода приходят из настроек сайта.
const theme = vi.hoisted(() => ({ contacts: {} as Record<string, unknown> }));
vi.mock("@/lib/theme", () => ({ getSiteTheme: async () => ({ contacts: theme.contacts }) }));
vi.mock("@/lib/info-pages", async (original) => ({
  ...(await original<typeof import("@/lib/info-pages")>()),
  getInfoPage: async () => null,
}));

import InfoPageView from "./page";

const params = (slug: string) => ({ params: Promise.resolve({ slug }) });

describe("Инфо-страница из кода", () => {
  beforeEach(() => {
    theme.contacts = {};
  });

  it("телефон, адрес и график берутся из настроек сайта", async () => {
    theme.contacts = {
      phone_display: "8 (8412) 99-88-77",
      address: "г. Пенза, ул. Новая, 5",
      schedule: "Пн–Пт 10:00–18:00",
    };
    const delivery = render(await InfoPageView(params("delivery")));
    // Карточка «Самовывоз из магазина».
    expect(delivery.container.textContent).toContain("г. Пенза, ул. Новая, 5. Пн–Пт 10:00–18:00.");
    expect(delivery.container.textContent).not.toContain("{{");
    delivery.unmount();

    const { container } = render(await InfoPageView(params("about")));
    expect(container.textContent).not.toContain("{{");
    expect(container.textContent).toContain("ул. Новая, 5");
    const calls = [...container.querySelectorAll('a[href^="tel:"]')];
    expect(calls.length).toBeGreaterThan(0);
    for (const link of calls) expect(link).toHaveAttribute("href", "tel:+78412998877");
  });

  it("без настроек — запасные контакты магазина, без меток", async () => {
    const { container } = render(await InfoPageView(params("about")));

    expect(container.textContent).not.toContain("{{");
    expect(screen.getAllByText(/1-й Онежский проезд, 12/).length).toBeGreaterThan(0);
    expect(container.querySelector('a[href="tel:+78412202087"]')).not.toBeNull();
  });
});
