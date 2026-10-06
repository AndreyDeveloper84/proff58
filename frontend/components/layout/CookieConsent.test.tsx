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

beforeEach(() => {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
  pathnameMock.mockReturnValue("/");
});
afterEach(() => {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
});

describe("CookieConsent", () => {
  it("без записи показывает баннер, с записью — нет", () => {
    const { unmount } = render(<CookieConsent initialConsent={null} />);
    expect(screen.getByRole("region", { name: "Согласие на cookie" })).toBeInTheDocument();
    unmount();

    const consent = writeConsent({ analytics: false });
    render(<CookieConsent initialConsent={consent} />);
    expect(screen.queryByRole("region", { name: "Согласие на cookie" })).toBeNull();
  });

  it("«Принять все» включает аналитику и закрывает баннер", () => {
    render(<CookieConsent initialConsent={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Принять все" }));
    expect(readConsent()).toMatchObject({ analytics: true });
    expect(screen.queryByRole("region", { name: "Согласие на cookie" })).toBeNull();
  });

  it("«Только необходимые» записывает отказ от аналитики", () => {
    render(<CookieConsent initialConsent={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Только необходимые" }));
    expect(readConsent()).toMatchObject({ analytics: false });
  });

  it("кнопки согласия и отказа равнозначны: один стиль, один ряд", () => {
    render(<CookieConsent initialConsent={null} />);
    const accept = screen.getByRole("button", { name: "Принять все" });
    const decline = screen.getByRole("button", { name: "Только необходимые" });
    expect(accept.className).toBe(decline.className);
    expect(accept.parentElement).toBe(decline.parentElement);
  });

  it("«Настроить»: необходимые без переключателя, аналитика — переключатель, выбор сохраняется", () => {
    render(<CookieConsent initialConsent={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить" }));
    expect(screen.getByText("Всегда")).toBeInTheDocument();
    const toggle = screen.getByRole("switch", { name: "Аналитические" });
    expect(toggle).not.toBeChecked();
    expect(toggle).toHaveAccessibleDescription(/Яндекс.Метрика/);
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    expect(readConsent()).toMatchObject({ analytics: true });
  });

  it("повторное открытие показывает текущий выбор и даёт отозвать", () => {
    const consent = writeConsent({ analytics: true });
    render(<CookieConsent initialConsent={consent} />);
    act(() => openConsentSettings());
    const toggle = screen.getByRole("switch");
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    expect(readConsent()).toMatchObject({ analytics: false });
  });

  it("кнопка «Настройки cookie» открывает баннер", () => {
    const consent = writeConsent({ analytics: false });
    render(
      <>
        <CookieSettingsButton />
        <CookieConsent initialConsent={consent} />
      </>,
    );
    expect(screen.queryByRole("region", { name: "Согласие на cookie" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Настройки cookie" }));
    expect(screen.getByRole("region", { name: "Согласие на cookie" })).toBeInTheDocument();
  });

  it("запись старой версии — баннер показывается снова", () => {
    document.cookie = `${CONSENT_COOKIE}=${encodeURIComponent(
      JSON.stringify({ v: 0, analytics: true, ts: 1 }),
    )}; Path=/`;
    render(<CookieConsent initialConsent={null} />);
    expect(screen.getByRole("region", { name: "Согласие на cookie" })).toBeInTheDocument();
  });

  it("ссылка на политику и описание связаны с регионом", () => {
    render(<CookieConsent initialConsent={null} />);
    const region = screen.getByRole("region", { name: "Согласие на cookie" });
    const link = screen.getByRole("link", {
      name: "Политика конфиденциальности",
    });
    expect(link).toHaveAttribute("href", "/info/privacy");
    expect(region.getAttribute("aria-describedby")).toBeTruthy();
  });

  it("не перекрывает нижние панели: отступ зависит от маршрута", () => {
    pathnameMock.mockReturnValue("/cart");
    const { unmount } = render(<CookieConsent initialConsent={null} />);
    expect(screen.getByRole("region", { name: "Согласие на cookie" }).className).toContain(
      "bottom-[136px]",
    );
    unmount();
    pathnameMock.mockReturnValue("/checkout");
    render(<CookieConsent initialConsent={null} />);
    expect(screen.getByRole("region", { name: "Согласие на cookie" }).className).toContain(
      "bottom-[72px]",
    );
  });
});
