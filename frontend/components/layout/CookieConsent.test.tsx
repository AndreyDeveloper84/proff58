import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pathnameMock = vi.fn(() => "/");
vi.mock("next/navigation", () => ({ usePathname: () => pathnameMock() }));

import {
  CONSENT_COOKIE,
  openConsentSettings,
  readConsent,
  writeConsent,
} from "@/lib/cookie-consent";
import { CookieConsent } from "./CookieConsent";
import { CookieSettingsButton } from "./CookieSettingsButton";

const region = () => screen.queryByRole("region", { name: "Используем cookie" });

beforeEach(() => {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
  pathnameMock.mockReturnValue("/");
});
afterEach(() => {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
});

describe("CookieConsent", () => {
  it("без записи показывает карточку, с записью — нет", () => {
    const { unmount } = render(<CookieConsent initialConsent={null} />);
    expect(region()).toBeInTheDocument();
    unmount();

    const consent = writeConsent({ analytics: false });
    render(<CookieConsent initialConsent={consent} />);
    expect(region()).toBeNull();
  });

  it("текст и ссылка по макету: заголовок, две строки, политика", () => {
    render(<CookieConsent initialConsent={null} />);
    expect(screen.getByRole("heading", { name: "Используем cookie" })).toBeInTheDocument();
    expect(screen.getByText(/Для работы корзины и входа на сайт\./)).toBeInTheDocument();
    expect(
      screen.getByText(/Аналитика помогает улучшать магазин — только с вашего согласия\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Политика конфиденциальности" })).toHaveAttribute(
      "href",
      "/info/privacy",
    );
    // Регион назван заголовком, не отдельной подписью.
    const section = region()!;
    expect(section.getAttribute("aria-labelledby")).toBe(
      screen.getByRole("heading", { name: "Используем cookie" }).id,
    );
  });

  it("ровно две кнопки, без «Настроить» и крестика", () => {
    render(<CookieConsent initialConsent={null} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Только необходимые", "Принять все"]);
    expect(screen.queryByText(/Настроить/)).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("«Принять все» включает аналитику и закрывает карточку", () => {
    render(<CookieConsent initialConsent={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Принять все" }));
    expect(readConsent()).toMatchObject({ analytics: true });
    expect(region()).toBeNull();
  });

  it("«Только необходимые» записывает отказ от аналитики и закрывает карточку", () => {
    render(<CookieConsent initialConsent={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Только необходимые" }));
    expect(readConsent()).toMatchObject({ analytics: false });
    expect(region()).toBeNull();
  });

  it("повторное открытие из подвала даёт изменить выбор", () => {
    const consent = writeConsent({ analytics: true });
    render(
      <>
        <CookieSettingsButton />
        <CookieConsent initialConsent={consent} />
      </>,
    );
    expect(region()).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Настройки cookie" }));
    expect(region()).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Только необходимые" }));
    expect(readConsent()).toMatchObject({ analytics: false });
    expect(region()).toBeNull();
  });

  it("событие открытия без кнопки тоже работает", () => {
    const consent = writeConsent({ analytics: false });
    render(<CookieConsent initialConsent={consent} />);
    act(() => openConsentSettings());
    expect(region()).toBeInTheDocument();
  });

  it("запись старой версии — карточка показывается снова", () => {
    document.cookie = `${CONSENT_COOKIE}=${encodeURIComponent(
      JSON.stringify({ v: 0, analytics: true, ts: 1 }),
    )}; Path=/`;
    render(<CookieConsent initialConsent={null} />);
    expect(region()).toBeInTheDocument();
  });

  it("не перекрывает нижние панели на мобильном: отступ зависит от маршрута", () => {
    pathnameMock.mockReturnValue("/cart");
    const { unmount } = render(<CookieConsent initialConsent={null} />);
    expect(region()!.className).toContain("bottom-[calc(136px_+_12px)]");
    unmount();
    pathnameMock.mockReturnValue("/checkout");
    render(<CookieConsent initialConsent={null} />);
    expect(region()!.className).toContain("bottom-[calc(72px_+_12px)]");
  });
});
