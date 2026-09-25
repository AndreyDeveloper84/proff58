import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_TOAST_MS,
  dismissToast,
  getToast,
  pauseToast,
  resumeToast,
  showManualCopy,
  showToast,
  subscribeToast,
} from "./toast";

describe("lib/toast — единственное уведомление", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    dismissToast();
    vi.useRealTimers();
  });

  it("по умолчанию скрывается само через 4 с", () => {
    expect(DEFAULT_TOAST_MS).toBe(4000);
    showToast("Выбранные товары удалены");
    expect(getToast()).toMatchObject({ kind: "success", message: "Выбранные товары удалены" });

    vi.advanceTimersByTime(3999);
    expect(getToast()).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(getToast()).toBeNull();
  });

  it("durationMs задаёт своё время", () => {
    showToast("Коротко", { durationMs: 1000 });
    vi.advanceTimersByTime(1000);
    expect(getToast()).toBeNull();
  });

  it("новое сообщение заменяет прежнее без стопки и перезапускает таймер", () => {
    showToast("Первое");
    const first = getToast();
    vi.advanceTimersByTime(3000);
    showToast("Второе");

    const second = getToast();
    expect(second).toMatchObject({ message: "Второе" });
    expect(second?.id).not.toBe(first?.id);

    // Таймер первого (оставалась 1 с) не должен погасить второе.
    vi.advanceTimersByTime(1000);
    expect(getToast()).toBe(second);
    vi.advanceTimersByTime(3000);
    expect(getToast()).toBeNull();
  });

  it("пауза запоминает остаток, resume досчитывает его", () => {
    showToast("Пауза");
    vi.advanceTimersByTime(1500);
    pauseToast();

    vi.advanceTimersByTime(60_000);
    expect(getToast()).not.toBeNull();

    resumeToast();
    vi.advanceTimersByTime(2499);
    expect(getToast()).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(getToast()).toBeNull();
  });

  it("новое сообщение сбрасывает паузу и идёт полные 4 с", () => {
    showToast("Первое");
    vi.advanceTimersByTime(3500);
    pauseToast();
    showToast("Второе");

    // Прежняя пауза не действует: таймер идёт без resume.
    vi.advanceTimersByTime(3999);
    expect(getToast()).toMatchObject({ message: "Второе" });
    vi.advanceTimersByTime(1);
    expect(getToast()).toBeNull();

    // И отложенный resume от старой паузы не воскрешает таймер.
    resumeToast();
    expect(getToast()).toBeNull();
  });

  it("повторная пауза и resume без паузы ничего не ломают", () => {
    showToast("Сообщение");
    resumeToast(); // паузы не было — таймер тот же
    vi.advanceTimersByTime(2000);
    pauseToast();
    pauseToast(); // вторая пауза не обнуляет остаток
    resumeToast();
    vi.advanceTimersByTime(2000);
    expect(getToast()).toBeNull();
  });

  it("ручной режим висит без таймера, пауза/resume его не трогают", () => {
    showManualCopy("Скопируйте вручную", "8 (8412) 20-20-87");
    pauseToast();
    resumeToast();
    vi.advanceTimersByTime(60_000);
    expect(getToast()).toMatchObject({ kind: "manual", value: "8 (8412) 20-20-87" });
  });

  it("dismissToast снимает уведомление и оповещает подписчиков", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToast(listener);
    showToast("Сообщение");
    dismissToast();
    expect(getToast()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    showToast("Ещё");
    expect(listener).toHaveBeenCalledTimes(2);
  });
});
