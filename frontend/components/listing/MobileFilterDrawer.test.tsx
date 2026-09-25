import { createRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MobileFilterDrawer } from "./MobileFilterDrawer";

// §4: drawer фильтров — рендер по open, счётчик в кнопке применения, закрытие по
// Escape и по кнопке «Показать N товаров».
describe("MobileFilterDrawer", () => {
  const base = {
    total: 24,
    onReset: () => {},
    triggerRef: createRef<HTMLButtonElement>(),
    chips: [],
  };

  it("не рендерится при open=false", () => {
    const { container } = render(
      <MobileFilterDrawer open={false} onClose={() => {}} {...base}>
        тело
      </MobileFilterDrawer>,
    );
    expect(container.firstChild).toBeNull();
  });

  it("показывает dialog и кнопку применения со счётчиком", () => {
    render(
      <MobileFilterDrawer open onClose={() => {}} {...base}>
        тело
      </MobileFilterDrawer>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Показать 24 товара")).toBeInTheDocument();
  });

  it("закрывается по Escape", () => {
    const onClose = vi.fn();
    render(
      <MobileFilterDrawer open onClose={onClose} {...base}>
        тело
      </MobileFilterDrawer>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("закрывается по кнопке применения", () => {
    const onClose = vi.fn();
    render(
      <MobileFilterDrawer open onClose={onClose} {...base}>
        тело
      </MobileFilterDrawer>,
    );
    fireEvent.click(screen.getByText("Показать 24 товара"));
    expect(onClose).toHaveBeenCalled();
  });
});
