import { useId } from "react";

import { cn } from "@/lib/utils";

// SP2 (#39): обёртка поля формы — label + контрол + подсказка/ошибка. Связывает
// label с контролом по id и прокидывает aria-describedby на сообщение об ошибке.
// Использование: <Field label="Телефон" error={errors.phone}>{(id) => <Input id={id} .../>}</Field>
export function Field({
  label,
  error,
  hint,
  required,
  className,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  className?: string;
  children: (id: string) => React.ReactNode;
}) {
  const id = useId();
  const msgId = `${id}-msg`;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink-2">
        {label}
        {required && <span className="ml-0.5 text-danger">*</span>}
      </label>
      {children(id)}
      {error ? (
        <p id={msgId} className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={msgId} className="text-xs text-ink-3">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
