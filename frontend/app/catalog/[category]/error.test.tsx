import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

import CatalogError from "./error";

describe("CatalogError — кнопка «Повторить»", () => {
  it("заново запрашивает страницу с сервера, а не только сбрасывает ошибку", () => {
    // Регрессия: reset() без router.refresh() перерисовывал сегмент из того же
    // сломанного ответа — кнопка выглядела рабочей, но ничего не меняла.
    const reset = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(<CatalogError error={new Error("boom")} reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: /повторить/i }));

    expect(refreshMock).toHaveBeenCalledTimes(1);
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
