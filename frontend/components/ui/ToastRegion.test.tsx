import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dismissToast, getToast, showManualCopy, showToast } from "@/lib/toast";
import { ToastRegion } from "./ToastRegion";

const live = () => screen.getByTestId("toast-live");
const card = () => screen.getByTestId("toast-card");

describe("ToastRegion", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    act(() => dismissToast());
    vi.useRealTimers();
  });

  it("live-область стоит в разметке заранее, пустая и вежливая", () => {
    render(<ToastRegion />);
    expect(live()).toHaveAttribute("aria-live", "polite");
    expect(live()).toHaveAttribute("aria-atomic", "true");
    expect(live()).toBeEmptyDOMElement();
    expect(screen.queryByRole("button", { name: "Закрыть уведомление" })).toBeNull();
  });

  it("в live-области только текст; у сообщения нет role; кнопка закрытия — вне области", () => {
    render(<ToastRegion />);
    act(() => showToast("Выбранные товары удалены"));

    expect(live().textContent).toBe("Выбранные товары удалены");
    expect(live().querySelector("[role]")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();

    const close = screen.getByRole("button", { name: "Закрыть уведомление" });
    expect(live().contains(close)).toBe(false);
    // Но в той же визуальной карточке.
    expect(card().contains(close)).toBe(true);
    expect(card().contains(live())).toBe(true);
  });

  it("кнопка закрытия убирает уведомление", () => {
    render(<ToastRegion />);
    act(() => showToast("Сообщение"));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть уведомление" }));
    expect(live()).toBeEmptyDOMElement();
    expect(getToast()).toBeNull();
  });

  it("ручной режим: одно объявление без role=alert, поле с текстом вне live-области", () => {
    render(<ToastRegion />);
    act(() => showManualCopy("Не удалось скопировать автоматически.", "8 (8412) 20-20-87"));

    expect(live().textContent).toBe("Не удалось скопировать автоматически.");
    expect(screen.queryByRole("alert")).toBeNull();
    const input = screen.getByLabelText("Текст для копирования вручную") as HTMLInputElement;
    expect(input.value).toBe("8 (8412) 20-20-87");
    expect(live().contains(input)).toBe(false);
    expect(document.activeElement).toBe(input);
  });

  it("hover по карточке ставит таймер на паузу, уход курсора досчитывает остаток", () => {
    render(<ToastRegion />);
    act(() => showToast("Сообщение"));
    act(() => vi.advanceTimersByTime(1000));

    fireEvent.mouseEnter(card());
    act(() => vi.advanceTimersByTime(10_000));
    expect(live()).toHaveTextContent("Сообщение");

    fireEvent.mouseLeave(card());
    act(() => vi.advanceTimersByTime(2999));
    expect(live()).toHaveTextContent("Сообщение");
    act(() => vi.advanceTimersByTime(1));
    expect(live()).toBeEmptyDOMElement();
  });

  it("фокус внутри карточки держит паузу, пока не уйдёт наружу (и курсор тоже)", () => {
    render(
      <>
        <button type="button">Снаружи</button>
        <ToastRegion />
      </>,
    );
    act(() => showToast("Сообщение"));
    const close = screen.getByRole("button", { name: "Закрыть уведомление" });

    act(() => close.focus());
    fireEvent.mouseEnter(card());
    act(() => vi.advanceTimersByTime(10_000));
    expect(live()).toHaveTextContent("Сообщение");

    // Фокус ушёл, но курсор ещё на карточке — пауза держится.
    act(() => screen.getByRole("button", { name: "Снаружи" }).focus());
    act(() => vi.advanceTimersByTime(10_000));
    expect(live()).toHaveTextContent("Сообщение");

    fireEvent.mouseLeave(card());
    act(() => vi.advanceTimersByTime(4000));
    expect(live()).toBeEmptyDOMElement();
  });

  it("клики принимает только карточка: обёртка прозрачна для указателя", () => {
    render(<ToastRegion />);
    act(() => showToast("Сообщение"));
    expect(card().className).toContain("pointer-events-auto");
    expect(card().parentElement?.className).toContain("pointer-events-none");
    expect(card().parentElement?.className).toContain("fixed");
  });
});
