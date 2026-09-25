import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/account/profile" }));
vi.mock("@/components/layout/MobileBottomNav", () => ({ MobileBottomNav: () => null }));

import { StorefrontProvider } from "@/components/site/StorefrontProvider";
import { resolveStorefront } from "@/lib/site";
import { AccountShell } from "./AccountShell";

// T4: раздел отзывов отключён владельцем — пункта в меню ЛК нет, пока флаг выключен.
describe("AccountShell: пункт «Отзывы»", () => {
  it("скрыт по умолчанию (раздел выключен)", () => {
    render(
      <AccountShell title="Т">
        <div />
      </AccountShell>,
    );
    expect(screen.queryByRole("link", { name: /Отзывы/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Заказы/ })).toBeInTheDocument();
  });

  it("появляется только при включённом флаге из настроек сайта", () => {
    render(
      <StorefrontProvider value={resolveStorefront({ features: { reviews: true } })}>
        <AccountShell title="Т">
          <div />
        </AccountShell>
      </StorefrontProvider>,
    );
    expect(screen.getByRole("link", { name: /Отзывы/ })).toHaveAttribute("href", "/account/reviews");
  });
});
