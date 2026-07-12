import { AlertTriangle, CheckCircle2, PackageOpen } from "lucide-react";

import { cn } from "@/lib/utils";

import { Spinner } from "./spinner";

// SP2 (#39) / SP2.1 (#474): стандартные состояния экрана — empty / error / loading /
// success. Единый вид для каталога, карточки, корзины, checkout. У каждого — понятный
// визуальный маркер (иконка/спиннер); все принимают optional action.

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
  const iconColor =
    tone === "danger" ? "text-danger" : tone === "success" ? "text-brand" : "text-ink-3";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        className,
      )}
    >
      {icon && <div className={iconColor}>{icon}</div>}
      <div className="space-y-1">
        <p className={cn("text-base font-semibold", titleColor)}>{title}</p>
        {description && <p className="text-sm text-ink-2">{description}</p>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function EmptyState({
  icon,
  ...props
}: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <StateShell
      tone="muted"
      icon={icon ?? <PackageOpen className="h-10 w-10" aria-hidden />}
      {...props}
    />
  );
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
  return (
    <StateShell
      tone="danger"
      icon={<AlertTriangle className="h-10 w-10" aria-hidden />}
      title={title}
      description={description}
      {...props}
    />
  );
}

export function SuccessState(props: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <StateShell
      tone="success"
      icon={<CheckCircle2 className="h-10 w-10" aria-hidden />}
      {...props}
    />
  );
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
      role="status"
      aria-busy="true"
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
