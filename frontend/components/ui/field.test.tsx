import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "./field";
import { Input } from "./input";

// SP2.1 (#474): a11y-контракт Field — связь label↔контрол, error/hint через
// aria-describedby, проброс required и aria-invalid на контрол.

describe("Field a11y", () => {
  it("связывает label с контролом (label → id)", () => {
    render(<Field label="Телефон">{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText("Телефон");
    expect(input).toBeInTheDocument();
  });

  it("hint доступен через aria-describedby", () => {
    render(
      <Field label="Телефон" hint="Для связи по заказу">
        {(p) => <Input {...p} />}
      </Field>,
    );
    const input = screen.getByLabelText("Телефон");
    const describedById = input.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    expect(document.getElementById(describedById as string)).toHaveTextContent(
      "Для связи по заказу",
    );
  });

  it("error выставляет aria-invalid и доступен через aria-describedby", () => {
    render(
      <Field label="E-mail" error="Некорректный e-mail">
        {(p) => <Input {...p} />}
      </Field>,
    );
    const input = screen.getByLabelText(/E-mail/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedById = input.getAttribute("aria-describedby");
    expect(document.getElementById(describedById as string)).toHaveTextContent(
      "Некорректный e-mail",
    );
  });

  it("required пробрасывается на контрол", () => {
    render(<Field label="Имя" required>{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText(/Имя/);
    expect(input).toBeRequired();
  });

  it("без error/hint нет aria-describedby и aria-invalid", () => {
    render(<Field label="Город">{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText("Город");
    expect(input).not.toHaveAttribute("aria-describedby");
    expect(input).not.toHaveAttribute("aria-invalid");
  });
});
