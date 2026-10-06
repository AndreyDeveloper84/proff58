import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pathnameMock = vi.fn(() => "/");
vi.mock("next/navigation", () => ({ usePathname: () => pathnameMock() }));

import { analyticsCounter, setAnalyticsCounter, track } from "@/lib/analytics";
import { CONSENT_COOKIE, clearConsent, writeConsent } from "@/lib/cookie-consent";
import { METRIKA_SRC, YandexMetrika, hitPath } from "./YandexMetrika";

const ID = 12345;

function scriptTag(): HTMLScriptElement | null {
  return document.querySelector(`script[src="${METRIKA_SRC}"]`);
}

function ymCalls(): unknown[][] {
  return (window.ym?.a ?? []) as unknown[][];
}

beforeEach(() => {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
  delete window.ym;
  delete window[`disableYaCounter${ID}`];
  setAnalyticsCounter(null);
  pathnameMock.mockReturnValue("/");
  localStorage.clear();
});
afterEach(() => {
  scriptTag()?.remove();
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
});

describe("YandexMetrika", () => {
  it("без согласия скрипт не вставляется и track() молчит", () => {
    render(<YandexMetrika counterId={ID} initialConsent={null} />);
    expect(scriptTag()).toBeNull();
    expect(window.ym).toBeUndefined();
    track({
      name: "tool_type_select",
      payload: {
        category_slug: "a",
        tool_type_slug: null,
        tool_type_label: null,
        result_count: 0,
        previous_tool_type: null,
        active_filters_count: 0,
      },
    });
    expect(analyticsCounter()).toBeNull();
  });

  it("после согласия: init через очередь, скрипт вставлен, первый хит отправлен, track() работает", () => {
    render(<YandexMetrika counterId={ID} initialConsent={null} />);
    act(() => {
      writeConsent({ analytics: true });
    });
    expect(scriptTag()).not.toBeNull();
    expect(scriptTag()?.async).toBe(true);
    const calls = ymCalls();
    expect(calls[0]).toEqual([
      ID,
      "init",
      expect.objectContaining({ defer: true, webvisor: false }),
    ]);
    expect(calls[1]).toEqual([ID, "hit", "/"]);
    expect(analyticsCounter()).toBe(ID);

    track({
      name: "tool_type_select",
      payload: {
        category_slug: "dreli",
        tool_type_slug: "udarnye",
        tool_type_label: "Ударные",
        result_count: 10,
        previous_tool_type: null,
        active_filters_count: 0,
      },
    });
    expect(calls[2]?.slice(0, 3)).toEqual([ID, "reachGoal", "tool_type_select"]);
  });

  it("с согласием в cookie при загрузке — включается сразу, хиты без дублей и без идентификаторов", () => {
    const consent = writeConsent({ analytics: true });
    const { rerender } = render(<YandexMetrika counterId={ID} initialConsent={consent} />);
    expect(scriptTag()).not.toBeNull();
    const hits = () =>
      ymCalls()
        .filter((c) => c[1] === "hit")
        .map((c) => c[2]);
    expect(hits()).toEqual(["/"]);

    rerender(<YandexMetrika counterId={ID} initialConsent={consent} />);
    expect(hits()).toEqual(["/"]); // тот же путь — второго хита нет

    pathnameMock.mockReturnValue("/order/П-20261006-ABCDEF/thanks");
    rerender(<YandexMetrika counterId={ID} initialConsent={consent} />);
    expect(hits()).toEqual(["/", "/order/*"]);
  });

  it("отзыв: флаг disableYaCounter, cookie и localStorage _ym* удалены, track() выключен, страница перезагружается", () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, reload, protocol: "http:", hostname: "localhost" },
    });
    const consent = writeConsent({ analytics: true });
    render(<YandexMetrika counterId={ID} initialConsent={consent} />);
    document.cookie = "_ym_uid=abc; Path=/";
    localStorage.setItem("_ym_uid", "abc");
    localStorage.setItem("_ym_synced", "1");

    act(() => {
      writeConsent({ analytics: false });
    });

    expect(window[`disableYaCounter${ID}`]).toBe(true);
    expect(document.cookie).not.toContain("_ym_uid");
    expect(localStorage.getItem("_ym_uid")).toBeNull();
    expect(localStorage.getItem("_ym_synced")).toBeNull();
    expect(analyticsCounter()).toBeNull();
    expect(ymCalls().some((c) => c[1] === "destruct")).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: original,
    });
  });

  it("отзыв до вставки скрипта не перезагружает страницу", () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, reload, protocol: "http:", hostname: "localhost" },
    });
    render(<YandexMetrika counterId={ID} initialConsent={null} />);
    act(() => {
      writeConsent({ analytics: false });
    });
    expect(scriptTag()).toBeNull();
    expect(reload).not.toHaveBeenCalled();
    expect(window[`disableYaCounter${ID}`]).toBe(true);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: original,
    });
  });
});

describe("YandexMetrika: старые следы", () => {
  it("без согласия при загрузке удаляет оставшиеся _ym_* (истёкшее или другой версии согласие)", () => {
    document.cookie = "_ym_uid=old; Path=/";
    localStorage.setItem("_ym_uid", "old");
    render(<YandexMetrika counterId={ID} initialConsent={null} />);
    expect(document.cookie).not.toContain("_ym_uid");
    expect(localStorage.getItem("_ym_uid")).toBeNull();
    expect(scriptTag()).toBeNull();
  });

  it("сброс записи согласия при вставленном скрипте — как отзыв: перезагрузка", () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, reload, protocol: "http:", hostname: "localhost" },
    });
    const consent = writeConsent({ analytics: true });
    render(<YandexMetrika counterId={ID} initialConsent={consent} />);
    act(() => {
      clearConsent();
    });
    expect(reload).toHaveBeenCalledTimes(1);
    Object.defineProperty(window, "location", { configurable: true, value: original });
  });
});

describe("hitPath", () => {
  it("обобщает заказы и кабинет, остальное отдаёт как есть", () => {
    expect(hitPath("/order/П-1/thanks")).toBe("/order/*");
    expect(hitPath("/account/orders/П-1")).toBe("/account/*");
    expect(hitPath("/catalog/dreli")).toBe("/catalog/dreli");
  });
});
