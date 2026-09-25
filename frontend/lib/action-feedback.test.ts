import { afterEach, describe, expect, it, vi } from "vitest";

import { emitActionSuccess, subscribeActionSuccess } from "./action-feedback";

describe("шина «товар успешно добавлен»", () => {
  const unsubscribes: Array<() => void> = [];
  afterEach(() => {
    while (unsubscribes.length) unsubscribes.pop()!();
    vi.restoreAllMocks();
  });

  it("доставляет событие подписчикам и перестаёт после отписки", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeActionSuccess(listener);

    emitActionSuccess("cart");
    expect(listener).toHaveBeenCalledWith("cart");

    unsubscribe();
    emitActionSuccess("wishlist");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  // Издатели зовут emit внутри `.then(emit).catch(rollback)`: бросивший слушатель
  // иначе откатил бы уже сохранённое на сервере избранное.
  it("сбой одного слушателя не бросает наружу и не глушит остальных", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const broken = vi.fn(() => {
      throw new Error("декор сломался");
    });
    const healthy = vi.fn();
    unsubscribes.push(subscribeActionSuccess(broken), subscribeActionSuccess(healthy));

    expect(() => emitActionSuccess("compare")).not.toThrow();
    expect(healthy).toHaveBeenCalledWith("compare");
  });
});
