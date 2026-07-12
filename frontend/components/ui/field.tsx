import { useId } from "react";

import { cn } from "@/lib/utils";

// SP2.1 (#474): a11y-контракт поля формы. Field сам связывает label ↔ контрол и
// прокидывает контролу id/aria-describedby/aria-invalid/required через props-bag —
// вызывающий просто разворачивает их на контрол:
//   <Field label="Телефон" required error={err}>
//     {(p) => <Input {...p} placeholder="+7 …" />}
//   </Field>
export type FieldControlProps = {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  required?: boolean;
};

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
  children: (control: FieldControlProps) => React.ReactNode;
}) {
  const id = useId();
  const msgId = `${id}-msg`;
  const hasMsg = Boolean(error || hint);

  const control: FieldControlProps = {
    id,
    "aria-describedby": hasMsg ? msgId : undefined,
    "aria-invalid": error ? true : undefined,
    required: required || undefined,
  };

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink-2">
        {label}
        {required && <span className="ml-0.5 text-danger">*</span>}
      </label>
      {children(control)}
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
