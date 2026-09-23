import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CallLink, CopyContact } from "./CopyContact";
import { ToastRegion } from "@/components/ui/ToastRegion";
import { dismissToast } from "@/lib/toast";

// UX-03: телефон и адрес копируются по нажатию, уведомление — только после успеха.
const PHONE = "8 (8412) 20-20-87";
const ADDRESS = "г. Пенза, 1-й Онежский проезд, 12";

function setClipboard(writeText: unknown) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: writeText ? { writeText } : undefined,
  });
}

// Live-область уведомлений: всегда в разметке, внутри — только текст сообщения.
const live = () => screen.getByTestId("toast-live");

function renderAll() {
  return render(
    <>
      <CopyContact kind="phone" value={PHONE} />
      <CopyContact kind="address" value={ADDRESS}>
        Магазин на Онежском
      </CopyContact>
      <CallLink href="tel:+78412202087" />
      <ToastRegion />
    </>,
  );
}

describe("CopyContact (UX-03)", () => {
  beforeEach(() => {
    document.execCommand = vi.fn(() => false);
  });
  afterEach(() => {
    act(() => dismissToast());
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("копирует отображаемый номер — без tel: и служебных подписей", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать номер телефона/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован в буфер обмена"));
    expect(writeText).toHaveBeenCalledWith(PHONE);
  });

  it("по короткой подписи магазина копируется ПОЛНЫЙ адрес", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать адрес/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Адрес скопирован в буфер обмена"));
    expect(writeText).toHaveBeenCalledWith(ADDRESS);
  });

  it("уведомление об успехе не появляется, пока копирование не завершилось", async () => {
    let finish!: () => void;
    setClipboard(vi.fn(() => new Promise<void>((resolve) => (finish = resolve))));
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать номер телефона/ }));
    expect(live()).toBeEmptyDOMElement();

    await act(async () => finish());
    expect(live()).toHaveTextContent("Номер скопирован в буфер обмена");
  });

  it("запрет буфера: понятное сообщение и текст, выделенный для ручного копирования", async () => {
    setClipboard(vi.fn().mockRejectedValue(new Error("NotAllowedError")));
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать номер телефона/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Не удалось скопировать автоматически"));
    // Одно объявление: без role=alert внутри polite-региона.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Номер скопирован в буфер обмена")).not.toBeInTheDocument();
    const manual = screen.getByLabelText("Текст для копирования вручную") as HTMLInputElement;
    expect(manual.value).toBe(PHONE);
    expect(document.activeElement).toBe(manual);
  });

  it("без Clipboard API срабатывает запасной путь, и это тоже успех", async () => {
    setClipboard(undefined);
    document.execCommand = vi.fn(() => true);
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать адрес/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Адрес скопирован"));
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("повторные нажатия не копят очередь: уведомление одно", async () => {
    setClipboard(vi.fn().mockResolvedValue(undefined));
    renderAll();
    const phone = screen.getByRole("button", { name: /Скопировать номер телефона/ });

    for (let i = 0; i < 4; i++) {
      fireEvent.click(phone);
      await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    }
    fireEvent.click(screen.getByRole("button", { name: /Скопировать адрес/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Адрес скопирован"));
    expect(live()).not.toHaveTextContent("Номер скопирован");
    expect(screen.getAllByRole("button", { name: "Закрыть уведомление" })).toHaveLength(1);
  });

  it("уведомление само исчезает и закрывается кнопкой", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setClipboard(vi.fn().mockResolvedValue(undefined));
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать номер телефона/ }));
    await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть уведомление" }));
    expect(live()).toBeEmptyDOMElement();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать номер телефона/ }));
    await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    act(() => vi.advanceTimersByTime(4000));
    expect(live()).toBeEmptyDOMElement();
  });

  it("копирование — кнопка (клавиатура, фокус), звонок — отдельная tel-ссылка", () => {
    setClipboard(vi.fn().mockResolvedValue(undefined));
    renderAll();

    const phone = screen.getByRole("button", { name: /Скопировать номер телефона/ });
    phone.focus();
    expect(document.activeElement).toBe(phone);
    expect(phone).not.toHaveAttribute("href");
    expect(screen.getByRole("link", { name: "Позвонить" })).toHaveAttribute(
      "href",
      "tel:+78412202087",
    );
  });

  it("регион уведомлений стоит в разметке заранее и объявляется вежливо", () => {
    const { container } = renderAll();
    expect(container.querySelector('[aria-live="polite"]')).toBeInTheDocument();
  });
});
