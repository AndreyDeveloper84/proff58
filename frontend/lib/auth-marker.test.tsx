import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { accountLinkHref, useHasAuthMarker } from "./auth-marker";

function Probe({ path }: { path: string }) {
  const marker = useHasAuthMarker();
  return <a href={accountLinkHref(path, marker)}>кабинет</a>;
}

function setCookie(value: string) {
  document.cookie = value;
}

describe("маркер входа для ссылок в кабинет", () => {
  afterEach(() => {
    document.cookie = "auth=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("гостя ведёт на форму входа с возвратом туда, куда он шёл", async () => {
    render(<Probe path="/account/wishlist" />);

    await waitFor(() =>
      expect(screen.getByRole("link")).toHaveAttribute(
        "href",
        "/account/login?next=%2Faccount%2Fwishlist",
      ),
    );
  });

  it("с маркером входа ведёт прямо в кабинет", async () => {
    setCookie("auth=1");
    render(<Probe path="/account/profile" />);

    await waitFor(() => expect(screen.getByRole("link")).toHaveAttribute("href", "/account/profile"));
  });

  it("не путает похожие по началу cookie с маркером", async () => {
    // `authorized_by_smth=1` не должна читаться как `auth`.
    setCookie("authsomething=1");
    render(<Probe path="/account/profile" />);

    await waitFor(() =>
      expect(screen.getByRole("link")).toHaveAttribute(
        "href",
        "/account/login?next=%2Faccount%2Fprofile",
      ),
    );
    document.cookie = "authsomething=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("до гидратации ссылка остаётся прежней — разметка сервера и клиента совпадают", () => {
    // null = «ещё не знаем»: подменять href в первом рендере нельзя.
    expect(accountLinkHref("/account/profile", null)).toBe("/account/profile");
  });
});
