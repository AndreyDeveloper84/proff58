import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/refunds", () => ({
  getRefundState: vi.fn(),
  requestRefund: vi.fn(),
}));

import { getRefundState, requestRefund, type RefundState } from "@/lib/refunds";
import { RefundRequestBlock } from "./RefundRequestBlock";

const mockedState = getRefundState as unknown as ReturnType<typeof vi.fn>;
const mockedRequest = requestRefund as unknown as ReturnType<typeof vi.fn>;

const REASONS = [
  { value: "defect", label: "Брак или неисправность" },
  { value: "other", label: "Другое" },
];

const open: RefundState = {
  can_request: true,
  block_reason: null,
  deadline: null,
  reasons: REASONS,
  requests: [],
};

const pending: RefundState = {
  ...open,
  can_request: false,
  block_reason: "Заявка на возврат уже на рассмотрении.",
  requests: [
    {
      id: 1,
      status: "pending",
      status_label: "На рассмотрении",
      reason: "defect",
      reason_label: "Брак или неисправность",
      comment: "Искрит",
      amount: null,
      decision_comment: "",
      created_at: "2026-09-17T10:00:00+03:00",
      decided_at: null,
    },
  ],
};

describe("RefundRequestBlock", () => {
  beforeEach(() => {
    mockedState.mockReset();
    mockedRequest.mockReset();
  });

  it("не рисуется, если заказ не оплачен онлайн и заявок не было", async () => {
    mockedState.mockResolvedValue({ ...open, can_request: false });
    const { container } = render(
      <RefundRequestBlock orderNumber="П-1" currency="RUB" />,
    );
    await waitFor(() => expect(mockedState).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("отправляет заявку с причиной и показывает её статус", async () => {
    mockedState.mockResolvedValue(open);
    mockedRequest.mockResolvedValue(pending);
    const onChanged = vi.fn();
    render(
      <RefundRequestBlock
        orderNumber="П-1"
        currency="RUB"
        onChanged={onChanged}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "Вернуть деньги" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Отправить заявку" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Выберите причину");
    expect(mockedRequest).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Брак или неисправность"));
    fireEvent.change(screen.getByPlaceholderText("Что случилось с заказом"), {
      target: { value: " Искрит " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Отправить заявку" }));

    await screen.findByText("На рассмотрении");
    expect(mockedRequest).toHaveBeenCalledWith("П-1", "defect", "Искрит");
    expect(onChanged).toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "Вернуть деньги" }),
    ).not.toBeInTheDocument();
  });

  it("для «Другое» требует пояснение", async () => {
    mockedState.mockResolvedValue(open);
    render(<RefundRequestBlock orderNumber="П-1" currency="RUB" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Вернуть деньги" }),
    );
    fireEvent.click(screen.getByLabelText("Другое"));
    fireEvent.click(screen.getByRole("button", { name: "Отправить заявку" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Опишите");
    expect(mockedRequest).not.toHaveBeenCalled();
  });

  it("показывает ответ магазина при отказе и объясняет, почему нельзя подать снова", async () => {
    mockedState.mockResolvedValue({
      ...pending,
      block_reason: "Прошло больше 14 дней после получения заказа.",
      requests: [
        {
          ...pending.requests[0],
          status: "rejected",
          status_label: "Отклонена",
          decision_comment: "Товар был в употреблении",
        },
      ],
    });
    render(<RefundRequestBlock orderNumber="П-1" currency="RUB" />);
    expect(
      await screen.findByText("Ответ магазина: Товар был в употреблении"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Прошло больше 14 дней/)).toBeInTheDocument();
  });

  it("показывает сумму возврата", async () => {
    mockedState.mockResolvedValue({
      ...pending,
      block_reason: null,
      requests: [
        {
          ...pending.requests[0],
          status: "refunded",
          status_label: "Деньги возвращены",
          amount: "3000.00",
        },
      ],
    });
    render(<RefundRequestBlock orderNumber="П-1" currency="RUB" />);
    expect(await screen.findByText(/Вернули 3 000 ₽/)).toBeInTheDocument();
  });
});
