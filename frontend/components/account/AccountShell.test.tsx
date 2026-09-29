import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/account/profile" }));
vi.mock("@/components/layout/MobileBottomNav", () => ({ MobileBottomNav: () => null }));

import { AccountShell } from "./AccountShell";

// DRF-2635: раздел отзывов убран с сайта — пункта «Отзывы» в меню кабинета нет.
describe("AccountShell: меню кабинета", () => {
  it("без пункта «Отзывы»", () => {
    render(
      <AccountShell title="Т">
        <div />
      </AccountShell>,
    );
    expect(screen.queryByRole("link", { name: /Отзывы/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Заказы/ })).toBeInTheDocument();
  });
});
