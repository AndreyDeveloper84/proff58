import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CartLine } from "@/lib/types";
import { CartItemRow } from "./CartItemRow";

const line: CartLine = {
  id: 5,
  product_id: 42,
  name: "Аккумуляторная дрель",
  slug: "akkumulyatornaya-drel",
  quantity: 2,
  price_final: "12990.00",
  price_base: "13990.00",
  discount: "1000.00",
  price_type: "retail",
  currency: "RUB",
  line_total: "25980.00",
};

describe("CartItemRow", () => {
  it("показывает товар, количество, цены и выбранное состояние", () => {
    render(
      <CartItemRow
        line={line}
        selected
        onSelect={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getByText("Аккумуляторная дрель")).toBeInTheDocument();
    expect(screen.getByText("Код товара: 42")).toBeInTheDocument();
    expect(screen.getAllByText("25 980 ₽").length).toBeGreaterThan(0);
    expect(screen.getByRole("checkbox", { name: "Выбрать Аккумуляторная дрель" })).toBeChecked();
  });

  it("вызывает обработчики выбора, количества и удаления", async () => {
    const onSelect = vi.fn();
    const onUpdate = vi.fn();
    const onRemove = vi.fn();
    render(
      <CartItemRow
        line={line}
        selected={false}
        onSelect={onSelect}
        onUpdate={onUpdate}
        onRemove={onRemove}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Выбрать Аккумуляторная дрель" }));
    // Шаги идут по одному: пока запрос количества в полёте, следующий шаг
    // игнорируется (UX-06) — поэтому между кликами ждём завершения.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Увеличить количество" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Уменьшить количество" }));
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Удалить Аккумуляторная дрель из корзины" }),
    );

    expect(onSelect).toHaveBeenCalledWith(5, true);
    expect(onUpdate).toHaveBeenNthCalledWith(1, 5, 3);
    expect(onUpdate).toHaveBeenNthCalledWith(2, 5, 1);
    expect(onRemove).toHaveBeenCalledWith(5);
  });

  it("показывает настоящее фото товара, а без фото — «Фото готовится»", () => {
    const props = { selected: false, onSelect: vi.fn(), onUpdate: vi.fn(), onRemove: vi.fn() };
    const { container, rerender } = render(
      <CartItemRow line={{ ...line, image: "/media/products/drel.jpg" }} {...props} />,
    );
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toContain(encodeURIComponent("/media/products/drel.jpg"));
    expect(container.innerHTML).not.toContain("sample-tool");

    rerender(<CartItemRow line={{ ...line, image: null }} {...props} />);
    expect(screen.getByText("Фото готовится")).toBeInTheDocument();
  });

  // --- UX-06: ручной ввод количества ---

  const field = () => screen.getByRole("textbox", { name: "Количество: Аккумуляторная дрель" });

  function renderRow(onUpdate = vi.fn()) {
    const utils = render(
      <CartItemRow
        line={line}
        selected={false}
        onSelect={vi.fn()}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
      />,
    );
    return { onUpdate, ...utils };
  }

  it("количество — поле ввода с цифровой клавиатурой, а не текст", () => {
    renderRow();
    expect(field()).toHaveValue("2");
    expect(field()).toHaveAttribute("inputmode", "numeric");
  });

  it("набор символов не шлёт запросы; Enter отправляет итог один раз, blur следом не дублирует", async () => {
    let release!: () => void;
    const onUpdate = vi.fn(() => new Promise<void>((resolve) => (release = resolve)));
    renderRow(onUpdate);

    fireEvent.change(field(), { target: { value: "1" } });
    fireEvent.change(field(), { target: { value: "15" } });
    fireEvent.change(field(), { target: { value: "159" } });
    expect(onUpdate).not.toHaveBeenCalled();

    fireEvent.keyDown(field(), { key: "Enter" });
    fireEvent.blur(field());

    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate).toHaveBeenCalledWith(5, 159);
    // Пока идёт запрос, поле не disabled (фокус не теряется), а readOnly.
    expect(field()).not.toBeDisabled();
    expect(field()).toHaveAttribute("readonly");

    await act(async () => release());
  });

  it("уход из поля применяет новое число", () => {
    const { onUpdate } = renderRow();
    fireEvent.change(field(), { target: { value: "15" } });
    fireEvent.blur(field());
    expect(onUpdate).toHaveBeenCalledWith(5, 15);
  });

  it("то же самое число на сервер не отправляется", () => {
    const { onUpdate } = renderRow();
    fireEvent.change(field(), { target: { value: "2" } });
    fireEvent.blur(field());
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("пустое поле допустимо при наборе, при подтверждении возвращается прежнее число", () => {
    const { onUpdate } = renderRow();
    fireEvent.change(field(), { target: { value: "" } });
    expect(field()).toHaveValue("");

    fireEvent.blur(field());

    expect(onUpdate).not.toHaveBeenCalled();
    expect(field()).toHaveValue("2");
    expect(screen.getByRole("alert")).toHaveTextContent("Введите целое число от 1");
  });

  it.each(["0", "-3", "1.5", "1,5", "1e3", "abc", "12 шт", "9007199254740993"])(
    "невалидное «%s» не отправляется и товар не удаляет",
    (bad) => {
      const onRemove = vi.fn();
      const onUpdate = vi.fn();
      render(
        <CartItemRow
          line={line}
          selected={false}
          onSelect={vi.fn()}
          onUpdate={onUpdate}
          onRemove={onRemove}
        />,
      );
      fireEvent.change(field(), { target: { value: bad } });
      fireEvent.keyDown(field(), { key: "Enter" });

      expect(onUpdate).not.toHaveBeenCalled();
      expect(onRemove).not.toHaveBeenCalled();
      expect(field()).toHaveValue("2");
      expect(field()).toHaveAttribute("aria-invalid", "true");
    },
  );

  it("Escape отменяет редактирование, следующий blur ничего не шлёт", () => {
    const { onUpdate } = renderRow();
    fireEvent.change(field(), { target: { value: "77" } });
    fireEvent.keyDown(field(), { key: "Escape" });
    fireEvent.blur(field());

    expect(field()).toHaveValue("2");
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("отказ сервера: введённое не выдаётся за сохранённое", async () => {
    const onUpdate = vi.fn().mockResolvedValue(false);
    renderRow(onUpdate);
    fireEvent.change(field(), { target: { value: "500" } });
    fireEvent.keyDown(field(), { key: "Enter" });

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Не сохранено"));
    expect(field()).toHaveValue("2");
  });

  it("после успеха поле показывает число с сервера", async () => {
    const onUpdate = vi.fn().mockResolvedValue(true);
    const { rerender } = renderRow(onUpdate);
    fireEvent.change(field(), { target: { value: "15" } });
    fireEvent.keyDown(field(), { key: "Enter" });
    await waitFor(() => expect(field()).not.toHaveAttribute("readonly"));

    rerender(
      <CartItemRow
        line={{ ...line, quantity: 15, line_total: "194850.00" }}
        selected={false}
        onSelect={vi.fn()}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
      />,
    );
    expect(field()).toHaveValue("15");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ввёл число и сразу нажал «+»: уходит только введённое, отката к старому нет", async () => {
    let release!: () => void;
    const onUpdate = vi.fn(() => new Promise<void>((resolve) => (release = resolve)));
    renderRow(onUpdate);

    fireEvent.change(field(), { target: { value: "15" } });
    fireEvent.blur(field()); // mousedown по «+» сначала уводит фокус из поля
    fireEvent.click(screen.getByRole("button", { name: "Увеличить количество" }));

    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate).toHaveBeenCalledWith(5, 15);
    await act(async () => release());
  });

  it("быстрый двойной клик по «+» даёт одно изменение", async () => {
    let release!: () => void;
    const onUpdate = vi.fn(() => new Promise<void>((resolve) => (release = resolve)));
    renderRow(onUpdate);
    const plus = screen.getByRole("button", { name: "Увеличить количество" });

    fireEvent.click(plus);
    fireEvent.click(plus);

    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate).toHaveBeenCalledWith(5, 3);
    await act(async () => release());
  });
});
