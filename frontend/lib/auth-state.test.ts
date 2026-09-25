import { describe, expect, it } from "vitest";

import { accountLinkHref, authStateFromCookies, loginHref } from "./auth-state";

const withCookies = (...names: string[]) => (name: string) => names.includes(name);

describe("authStateFromCookies", () => {
  it("маркер входа — точно вошёл", () => {
    expect(authStateFromCookies(withCookies("auth", "sessionid"))).toBe("authenticated");
  });

  it("сессия без маркера — «может быть вошёл», а не гость", () => {
    // Именно этот случай уводил вошедшего на форму входа: маркер появился
    // позже сессии, и шапка считала человека гостем до перезагрузки.
    expect(authStateFromCookies(withCookies("sessionid"))).toBe("unknown");
  });

  it("без cookie — гость", () => {
    expect(authStateFromCookies(withCookies())).toBe("anonymous");
    expect(authStateFromCookies(withCookies("csrftoken"))).toBe("anonymous");
  });
});

describe("accountLinkHref", () => {
  it("гостя ведёт на форму входа с возвратом", () => {
    expect(accountLinkHref("/account/wishlist", "anonymous")).toBe(
      "/account/login?next=%2Faccount%2Fwishlist",
    );
  });

  it("вошедшего и «может быть вошёл» — по назначению", () => {
    expect(accountLinkHref("/account/wishlist", "authenticated")).toBe("/account/wishlist");
    expect(accountLinkHref("/account/wishlist", "unknown")).toBe("/account/wishlist");
  });
});

describe("loginHref", () => {
  it("внешний адрес в next не попадает", () => {
    expect(loginHref("https://example.com/")).toBe("/account/login");
    expect(loginHref()).toBe("/account/login");
  });
});
