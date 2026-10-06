import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CONSENT_CHANGE_EVENT,
  CONSENT_COOKIE,
  CONSENT_VERSION,
  clearConsent,
  onConsentChange,
  parseConsent,
  readConsent,
  writeConsent,
} from "./cookie-consent";

function rawCookie(): string {
  return document.cookie;
}

afterEach(() => {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
});

describe("cookie_consent", () => {
  it("без записи согласия нет", () => {
    expect(readConsent()).toBeNull();
  });

  it("записывает выбор с версией и атрибутами cookie", () => {
    const spy = vi.spyOn(document, "cookie", "set");
    writeConsent({ analytics: true });
    const written = spy.mock.calls[0][0];
    expect(written).toContain("Path=/");
    expect(written).toContain("SameSite=Lax");
    expect(written).toContain("Max-Age=31536000");
    expect(written).not.toContain("Domain="); // host-only: поддоменов у сайта нет
    expect(written).not.toContain("Secure"); // jsdom — http
    spy.mockRestore();
    expect(readConsent()).toMatchObject({
      v: CONSENT_VERSION,
      analytics: true,
    });
    expect(rawCookie()).toContain(CONSENT_COOKIE);
  });

  it("отказ от аналитики тоже запись, а не отсутствие согласия", () => {
    writeConsent({ analytics: false });
    expect(readConsent()).toMatchObject({ analytics: false });
  });

  it("запись другой версии или битый JSON — как отсутствие", () => {
    expect(parseConsent(encodeURIComponent(JSON.stringify({ v: 0, analytics: true })))).toBeNull();
    expect(parseConsent("%7Bnot-json")).toBeNull();
    expect(parseConsent(encodeURIComponent(JSON.stringify({ v: CONSENT_VERSION })))).toBeNull();
  });

  it("событие уходит при записи и при сбросе", () => {
    const seen: unknown[] = [];
    const off = onConsentChange((consent) => seen.push(consent));
    writeConsent({ analytics: true });
    clearConsent();
    off();
    writeConsent({ analytics: false });
    expect(seen).toHaveLength(2);
    expect(seen[0]).toMatchObject({ analytics: true });
    expect(seen[1]).toBeNull();
  });

  it("подписчик вне модуля слышит то же событие", () => {
    const handler = vi.fn();
    window.addEventListener(CONSENT_CHANGE_EVENT, handler);
    writeConsent({ analytics: true });
    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(CONSENT_CHANGE_EVENT, handler);
  });
});
