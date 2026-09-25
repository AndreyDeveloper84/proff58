import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitActionSuccess } from "@/lib/action-feedback";
import {
  ACTION_DURATION_MS,
  CartActionIcon,
  COMPARE_BARS,
  CompareActionIcon,
  HeaderBadge,
  WishlistActionIcon,
} from "./HeaderActionIcons";

const inner = (root: HTMLElement) => root.querySelector(".hdr-icon-inner")!;
const outer = (root: HTMLElement) => root.querySelector(".hdr-icon")!;

describe("иконки действий шапки", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("на маунте и при перерендере ничего не играет", () => {
    const { container, rerender } = render(<CartActionIcon className="h-5 w-5" />);
    expect(outer(container)).not.toHaveAttribute("data-acting");
    expect(inner(container)).not.toHaveAttribute("data-acting");

    rerender(<CartActionIcon className="h-5 w-5" />);
    expect(inner(container)).not.toHaveAttribute("data-acting");
  });

  it("успешное добавление помечает обёртки и снимает метку по таймеру", () => {
    const { container } = render(<CartActionIcon className="h-5 w-5" />);

    act(() => emitActionSuccess("cart"));
    expect(outer(container)).toHaveAttribute("data-acting", "true");
    expect(inner(container)).toHaveAttribute("data-acting", "true");

    act(() => vi.advanceTimersByTime(ACTION_DURATION_MS.cart));
    expect(outer(container)).not.toHaveAttribute("data-acting");
    expect(inner(container)).not.toHaveAttribute("data-acting");
    // Декор на месте, невидим и не кликабелен — за это отвечает CSS (.hdr-drop).
    expect(container.querySelector(".hdr-drop")).toHaveAttribute("aria-hidden");
  });

  it("чужое событие иконку не трогает", () => {
    const { container } = render(<WishlistActionIcon className="h-5 w-5" />);
    act(() => emitActionSuccess("cart"));
    expect(inner(container)).not.toHaveAttribute("data-acting");
  });

  // Два клика подряд: анимация начинается заново (новый узел), а таймер снятия
  // метки один — иначе первый таймер снял бы её посреди второго прогона.
  it("быстрые повторы перезапускают эффект без накопления таймеров", () => {
    const { container } = render(<WishlistActionIcon className="h-5 w-5" />);

    act(() => emitActionSuccess("wishlist"));
    const first = inner(container);
    act(() => vi.advanceTimersByTime(300));
    act(() => emitActionSuccess("wishlist"));
    const second = inner(container);

    expect(second).not.toBe(first);
    expect(vi.getTimerCount()).toBe(1);

    act(() => vi.advanceTimersByTime(ACTION_DURATION_MS.wishlist - 50));
    expect(second).toHaveAttribute("data-acting", "true"); // первый таймер не сработал
    act(() => vi.advanceTimersByTime(50));
    expect(second).not.toHaveAttribute("data-acting");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("размонтирование гасит таймер", () => {
    const { unmount } = render(<CartActionIcon className="h-5 w-5" />);
    act(() => emitActionSuccess("cart"));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  // Рисунок сравнения — тот же lucide chart-column, только столбики разнесены
  // по своим path, чтобы двигаться поодиночке; ось остаётся без анимации.
  it("иконка сравнения повторяет lucide chart-column: ось + три столбика", () => {
    const { container } = render(<CompareActionIcon className="h-5 w-5" />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveClass("lucide", "lucide-chart-column", "h-5", "w-5");
    expect(svg).toHaveAttribute("viewBox", "0 0 24 24");
    expect(svg).toHaveAttribute("stroke-width", "2");
    expect(svg).toHaveAttribute("aria-hidden", "true");

    const paths = Array.from(svg.querySelectorAll("path")).map((p) => p.getAttribute("d"));
    expect(paths).toEqual(["M3 3v16a2 2 0 0 0 2 2h16", ...COMPARE_BARS]);
    expect(svg.querySelectorAll("path.hdr-bar")).toHaveLength(3);
    expect(svg.querySelector("path:first-child")).not.toHaveClass("hdr-bar");
  });
});

describe("счётчик у иконки (HeaderBadge)", () => {
  const badge = (root: HTMLElement) => root.querySelector(".hdr-badge");

  it("на загрузке и при восстановлении списка не «прыгает»", () => {
    const { container, rerender } = render(<HeaderBadge count={0} kind="cart" />);
    expect(badge(container)).toBeNull();
    rerender(<HeaderBadge count={2} kind="cart" />);
    expect(badge(container)).toHaveTextContent("2");
    expect(badge(container)).not.toHaveAttribute("data-pop");
  });

  it("первое появление после добавления — с задержкой, смена числа — сразу", () => {
    const { container, rerender } = render(<HeaderBadge count={0} kind="cart" />);
    act(() => emitActionSuccess("cart"));
    rerender(<HeaderBadge count={1} kind="cart" />);
    expect(badge(container)).toHaveAttribute("data-pop", "delayed");

    act(() => emitActionSuccess("cart"));
    rerender(<HeaderBadge count={2} kind="cart" />);
    expect(badge(container)).toHaveAttribute("data-pop", "true");
    expect(badge(container)).toHaveTextContent("2");
  });

  it("быстрые повторы перезапускают pop новым узлом", () => {
    const { container, rerender } = render(<HeaderBadge count={1} kind="wishlist" />);
    act(() => emitActionSuccess("wishlist"));
    rerender(<HeaderBadge count={2} kind="wishlist" />);
    const first = badge(container);
    act(() => emitActionSuccess("wishlist"));
    rerender(<HeaderBadge count={3} kind="wishlist" />);
    expect(badge(container)).not.toBe(first);
  });

  it("чужое событие, удаление и смена количества без добавления pop не дают", () => {
    const { container, rerender } = render(<HeaderBadge count={1} kind="compare" />);
    act(() => emitActionSuccess("cart"));
    rerender(<HeaderBadge count={1} kind="compare" />);
    expect(badge(container)).not.toHaveAttribute("data-pop");

    rerender(<HeaderBadge count={3} kind="compare" />);
    expect(badge(container)).not.toHaveAttribute("data-pop");
    rerender(<HeaderBadge count={0} kind="compare" />);
    expect(badge(container)).toBeNull();
  });

  it("после опустошения списка старый pop забывается", () => {
    const { container, rerender } = render(<HeaderBadge count={0} kind="cart" />);
    act(() => emitActionSuccess("cart"));
    rerender(<HeaderBadge count={1} kind="cart" />);
    rerender(<HeaderBadge count={0} kind="cart" />);
    rerender(<HeaderBadge count={1} kind="cart" />); // соседняя вкладка / загрузка
    expect(badge(container)).not.toHaveAttribute("data-pop");
  });

  it("больше 99 показывает 99+", () => {
    const { container } = render(<HeaderBadge count={120} kind="cart" />);
    expect(badge(container)).toHaveTextContent("99+");
  });
});
