import { cn } from "@/lib/utils";

import { Spinner } from "./spinner";

// SP2 (#39): стандартные состояния экрана — empty / error / loading / success.
// Единый вид для каталога, карточки, корзины, checkout — фронт не изобретает
// заглушки заново. Все принимают optional action (кнопка/ссылка) и children.

function StateShell({
  icon,
  title,
  description,
  action,
  tone,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  tone?: "muted" | "danger" | "success";
  className?: string;
}) {
  const titleColor =
    tone === "danger" ? "text-danger" : tone === "success" ? "text-brand" : "text-ink";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        className,
      )}
    >
      {icon && <div className="text-ink-3">{icon}</div>}
      <div className="space-y-1">
        <p className={cn("text-base font-semibold", titleColor)}>{title}</p>
        {description && <p className="text-sm text-ink-2">{description}</p>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function EmptyState(props: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return <StateShell tone="muted" {...props} />;
}

export function ErrorState({
  title = "Что-то пошло не так",
  description = "Попробуйте обновить страницу или повторить позже.",
  ...props
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return <StateShell tone="danger" title={title} description={description} {...props} />;
}

export function SuccessState(props: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return <StateShell tone="success" {...props} />;
}

export function LoadingState({
  label = "Загрузка…",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-12 text-center text-ink-2",
        className,
      )}
    >
      <Spinner size="lg" className="text-accent" />
      <p className="text-sm">{label}</p>
    </div>
  );
}
